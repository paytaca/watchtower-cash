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
    MultisigTransactionProposalSerializer,
    SignatureSerializer
)
from multisig.models.wallet import MultisigWallet

LOGGER = logging.getLogger(__name__)
MAIN_JS_SERVER = 'http://localhost:3000'

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
                f'{MAIN_JS_SERVER}/multisig/utils/get-transaction-hash',
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
        proposal = self.get_object(pk)
        serializer = MultisigTransactionProposalSerializer(proposal)
        return Response(serializer.data)

    def delete(self, request, pk):
        proposal = self.get_object(pk)
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


