import logging
import requests
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotFound
from multisig.models import MultisigTransactionProposal, Signer, Signature
from multisig.serializers import (
    MultisigWalletSerializer,
    MultisigTransactionProposalSerializer,
    SignatureSerializer
)
from multisig.models.wallet import MultisigWallet

LOGGER = logging.getLogger(__name__)
MULTISIG_JS_SERVER = 'http://localhost:3004'

class MultisigTransactionProposalListCreateView(APIView):

    def get_wallet(self, wallet_identifier): 
        wallet = None

        if wallet_identifier.isdigit():
            wallet = get_object_or_404(MultisigWallet, id=int(wallet_identifier))
        else:
            wallet = get_object_or_404(MultisigWallet, locking_bytecode=wallet_identifier)

        return wallet

    def get(self, request, wallet_identifier):
        proposals = MultisigTransactionProposal.objects.all()
        
        if wallet_identifier.isdigit():
            proposals = proposals.filter(wallet__id=int(wallet_identifier))
        else:
            proposals = proposals.filter(wallet__locking_bytecode=wallet_identifier)
        wallet_address_index = request.query_params.get('wallet_address_index')

        if wallet_address_index != None:
            proposals = proposals.filter(wallet_address_index=wallet_address_index)

        serializer = MultisigTransactionProposalSerializer(proposals, many=True)
        return Response(serializer.data)

    def post(self, request, wallet_identifier):
        wallet = self.get_wallet(wallet_identifier)
        transaction_hash = None
        try:
            resp = requests.post(
                f'{MULTISIG_JS_SERVER}/multisig/utils/get-transaction-hash',
                data = {'transaction': request.data['transaction']}, timeout=5
            )
            resp = resp.json()
            transaction_hash = resp.get('transaction_hash')
            LOGGER.info(transaction_hash)   
        except Exception as e:
            return Response(
                {
                    "error": "Service unavailable",
                    "details": "An internal dependency is currently down. Please try again later."
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        


        proposal = MultisigTransactionProposal.objects.prefetch_related('signatures').filter(transaction_hash=transaction_hash)
        if proposal.exists():
            serializer = MultisigTransactionProposalSerializer(proposal.first())
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = MultisigTransactionProposalSerializer(data={ **request.data, 'transaction_hash': transaction_hash }, many=False)
        if serializer.is_valid():
            serializer.save(wallet=wallet)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        LOGGER.info(serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MultisigTransactionProposalDetailView(APIView):

    def get_object(self, proposal_identifier):
        if proposal_identifier.isdigit():
            return get_object_or_404(MultisigTransactionProposal, pk=proposal_identifier)
        return get_object_or_404(MultisigTransactionProposal, transaction_hash=proposal_identifier)

    def get(self, request, proposal_identifier):
        proposal = self.get_object(proposal_identifier)
        serializer = MultisigTransactionProposalSerializer(proposal)
        return Response(serializer.data)

    def delete(self, request, proposal_identifier):
        proposal = self.get_object(proposal_identifier)
        proposal.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SignerSignaturesAddView(APIView):

    def get_transaction_proposal(self, proposal_identifier):
        if proposal_identifier.isdigit():
            return get_object_or_404(MultisigTransactionProposal, pk=proposal_identifier)
        return get_object_or_404(MultisigTransactionProposal, transaction_hash=proposal_identifier)

    def post(self, request, proposal_identifier, signer_identifier):
        try:
            proposal = self.get_transaction_proposal(proposal_identifier)
            signer = get_object_or_404(Signer, entity_key=signer_identifier, wallet=proposal.wallet)
        except MultisigTransactionProposal.DoesNotExist:
            raise NotFound(f"MultisigTransactionProposal with id {proposal_id} not found.")
        except Signer.DoesNotExist:
            raise NotFound(f"Signer with entity key {signer_entity_key} not found.")
        data = request.data.copy()
        with transaction.atomic():
            signatures = []
            for signature_item in data:
                signature_instance, created = Signature.objects.get_or_create(
                    signer=signer,
                    transaction_proposal=proposal,
                    input_index=int(signature_item['inputIndex']),
                    defaults={
                    'signer': signer,
                    'transaction_proposal': proposal,
                    'input_index': int(signature_item['inputIndex']),
                    'signature_key': signature_item['sigKey'],
                    'signature_value': signature_item['sigValue']
                })
                serializer = SignatureSerializer(signature_instance)
                signatures.append(serializer.data)
            return Response(signatures, status=status.HTTP_200_OK)
 
class SignaturesAddView(APIView):
    def get_transaction_proposal(self, proposal_identifier):
        if proposal_identifier.isdigit():
            return get_object_or_404(MultisigTransactionProposal, pk=proposal_identifier)
        return get_object_or_404(MultisigTransactionProposal, transaction_hash=proposal_identifier)

    def post(self, request, proposal_identifier):
        try:
            proposal = self.get_transaction_proposal(proposal_identifier)
        except MultisigTransactionProposal.DoesNotExist:
            raise NotFound(f"MultisigTransactionProposal with id {proposal_id} not found.")
        data = request.data.copy()
        with transaction.atomic():
            signatures = []
            for signature_item in data:
                signer_entity_key =  signature_item['sigKey'].split('.')[0].replace('key', 'signer_')
                signer = get_object_or_404(Signer, entity_key=signer_entity_key, wallet=proposal.wallet)
                signature_instance, created = Signature.objects.get_or_create(
                    signer=signer,
                    transaction_proposal=proposal,
                    input_index=int(signature_item['inputIndex']),
                    defaults={
                    'signer': signer,
                    'transaction_proposal': proposal,
                    'input_index': int(signature_item['inputIndex']),
                    'signature_key': signature_item['sigKey'],
                    'signature_value': signature_item['sigValue']
                })
                serializer = SignatureSerializer(signature_instance)
                signatures.append(serializer.data)
            return Response(signatures, status=status.HTTP_200_OK)

class BroadcastTransactionProposalView(APIView):
    
    def get_transaction_proposal(self, proposal_identifier):
        if proposal_identifier.isdigit():
            return get_object_or_404(MultisigTransactionProposal, id=int(proposal_identifier))
        return get_object_or_404(MultisigTransactionProposal, transaction_hash=proposal_identifier)


    def post(self, request, proposal_identifier):

        proposal = self.get_transaction_proposal(proposal_identifier)
        proposal_serializer = MultisigTransactionProposalSerializer(proposal, many=False)
        wallet_serializer = MultisigWalletSerializer(proposal.wallet, many=False)
        data = {
            'multisigTransaction': proposal_serializer.data,
            'multisigWallet': wallet_serializer.data
        }

        # finalize transaction
        # update transaction_proposal add signed_transaction, txid
        if not proposal.signed_transaction:
            resp = requests.post(
                f'{MULTISIG_JS_SERVER}/multisig/transaction/finalize',
                json=data,
                timeout=5
            )
            if resp.status_code != 200:
                Response({'error': 'Internal service error' }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        
            finalization_result = resp.json()
            
            LOGGER.info(finalization_result)
            if finalization_result['unsignedTransactionHash'] != proposal.transaction_hash:
                return Response(
                    {
                        'error': 'Internal service error. Proposal transaction hash does not match transaction being finalized' 
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
        
              
            if finalization_result['success'] and finalization_result['vmVerificationResult']:
                proposal.signed_transaction = finalization_result['signedTransaction']
                proposal.signed_transaction_hash = finalization_result['signedTransactionHash']
                proposal.save(update_fields=['signed_transaction', 'signed_transaction_hash'])    
        
        signing_progress_resp = requests.post(
            f'{MULTISIG_JS_SERVER}/multisig/transaction/get-signing-progress',
            json=data,
            timeout=5
        )
 
        return Response({**signing_progress_resp.json()})
 

