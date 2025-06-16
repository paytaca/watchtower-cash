import logging
import requests
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse
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
import multisig.js_client as js_client

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
            resp = js_client.get_transaction_hash(request.data['transaction'])
            resp = resp.json()
            transaction_hash = resp.get('transaction_hash')
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

        serializer = MultisigTransactionProposalSerializer(data={ **request.data, 'transactionHash': transaction_hash }, many=False)
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
        if not proposal.deleted_at:
            proposal.soft_delete()
        else:
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

        if proposal.signing_progress == MultisigTransactionProposal.SigningProgress.FULLY_SIGNED:
            signature_serializer = SignatureSerializer(proposal.signatures, many=True)
            return Response(signature_serializer.data, status=HTTP_200_OK)

        with transaction.atomic():
            signatures = []
            for signature_item in request.data:
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

class FinalizeTransactionProposalView(APIView):
    
    def get_transaction_proposal(self, proposal_identifier):
        if proposal_identifier.isdigit():
            return get_object_or_404(MultisigTransactionProposal, id=int(proposal_identifier))
        return get_object_or_404(MultisigTransactionProposal, transaction_hash=proposal_identifier)
    
    def post(self, request, proposal_identifier):

        proposal = self.get_transaction_proposal(proposal_identifier)
        
        
        if proposal.signed_transaction:
            return Response({
                'signedTransaction': proposal.signed_transaction,
                'signedTransactionHash': proposal.signed_transaction_hash,
                'unsignedTransactionHash': proposal.transaction,
                'vmVerificationSuccess': True,
                'success': True
            })
        
        proposal_serializer = MultisigTransactionProposalSerializer(proposal, many=False)
        wallet_serializer = MultisigWalletSerializer(proposal.wallet, many=False)
        #data = {
        #    'multisigTransaction': proposal_serializer.data,
        #    'multisigWallet': wallet_serializer.data
        #}

        try:
            #resp = requests.post(
            #    f'{MULTISIG_JS_SERVER}/multisig/transaction/finalize',
            #    json=data,
            #    timeout=5
            #)
            resp = js_client.finalize_transaction(proposal_serializer.data, wallet_serializer.data)
            if resp.status_code != 200:
                Response({'error': 'Internal service error' }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        
            final_compilation_result = resp.json()
            
            if final_compilation_result['unsignedTransactionHash'] != proposal.transaction_hash:
                return Response(
                    {
                        'error': 'Internal service error. Proposal transaction hash does not match transaction being finalized' 
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
        
              
            if final_compilation_result['success'] and final_compilation_result['vmVerificationSuccess']:
                proposal.signed_transaction = final_compilation_result['signedTransaction']
                proposal.signed_transaction_hash = final_compilation_result['signedTransactionHash']
                proposal.save(update_fields=['signed_transaction', 'signed_transaction_hash'])
            

            response_data = {
              'signedTransaction': final_compilation_result.get('signedTransaction', ''),
              'signedTransactionHash': final_compilation_result.get('signedTransactionHash', ''),
              'unsignedTransactionHash': final_compilation_result.get('unsignedTransactionHash', proposal.transaction),
              'success': final_compilation_result['success'],
              'vmVerificationSuccess': final_compilation_result['vmVerificationSuccess']
            }
        
            if final_compilation_result.get('errors'):
                response_data['errors'] = final_compilation_result['errors']
            return Response(response_data)

        except Exception as e:
            if not proposal.signed_transaction:
                return Response(
                    {
                        'error': 'Internal service error. Proposal transaction hash does not match transaction being finalized' 
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
        


class BroadcastTransactionProposalView(APIView):
    
    def get_transaction_proposal(self, proposal_identifier):
        if proposal_identifier.isdigit():
            return get_object_or_404(MultisigTransactionProposal, id=int(proposal_identifier))
        return get_object_or_404(MultisigTransactionProposal, transaction_hash=proposal_identifier)


    def post(self, request, proposal_identifier):

        proposal = self.get_transaction_proposal(proposal_identifier)
        proposal_serializer = MultisigTransactionProposalSerializer(proposal, many=False)
        wallet_serializer = MultisigWalletSerializer(proposal.wallet, many=False)
        
        #data = {
        #    'multisigTransaction': proposal_serializer.data,
        #    'multisigWallet': wallet_serializer.data
        #}

        if not proposal.signed_transaction:
            try:
                #resp = requests.post(
                #    f'{MULTISIG_JS_SERVER}/multisig/transaction/finalize',
                #    json=data,
                #    timeout=5
                #)
                resp = js_client.finalize_transaction(proposal_serializer.data, wallet_serializer.data)
                if resp.status_code != 200:
                    Response({'error': 'Internal service error' }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            
                final_compilation_result = resp.json()
                
                if final_compilation_result['unsignedTransactionHash'] != proposal.transaction_hash:
                    return Response(
                        {
                            'error': 'Internal service error. Proposal transaction hash does not match transaction being finalized' 
                        },
                        status=status.HTTP_503_SERVICE_UNAVAILABLE
                    )
            
                  
                if final_compilation_result['success'] and final_compilation_result['vmVerificationSuccess']:
                    proposal.signed_transaction = final_compilation_result['signedTransaction']
                    proposal.signed_transaction_hash = final_compilation_result['signedTransactionHash']
                    proposal.save(update_fields=['signed_transaction', 'signed_transaction_hash'])

            except Exception as e:
                if not proposal.signed_transaction:
                    return Response(
                        {
                            'error': 'Internal service error. Proposal transaction hash does not match transaction being finalized' 
                        },
                        status=status.HTTP_503_SERVICE_UNAVAILABLE
                    )
        
        url = request.build_absolute_uri(reverse('broadcast-transaction'))
        #signing_progress_resp = requests.post(
        #    f'{MULTISIG_JS_SERVER}/multisig/transaction/get-signing-progress',
        #    json=data,
        #    timeout=5
        #)
        signing_progress_resp = js_client.get_signing_progress(proposal_serializer.data, wallet_serializer.data)
        # TODO: for local test only, replace with existing tx broadcast logic
        broadcast_resp = requests.post(
            f'https://chipnet.watchtower.cash/api/broadcast/',
            json={ 'transaction': proposal.signed_transaction},
            timeout=5
        )
        broadcast_resp = broadcast_resp.json()
        if broadcast_resp['success']:
            proposal.txid = broadcast_resp['txid']
            proposal.broadcast_status = MultisigTransactionProposal.BroadcastStatus.DONE
            proposal.save(update_fields=['txid', 'status', 'broadcast_status'])
        LOGGER.info(broadcast_resp)
        if broadcast_resp.get('error') and broadcast_resp.get('error','').find('txn-already-known') != -1:
            if not proposal.txid:
                proposal.txid = proposal.signed_transaction_hash
            proposal.broadcast_status = MultisigTransactionProposal.BroadcastStatus.DONE
            proposal.save()
        return Response({
            **broadcast_resp,
            'transactionProposal': proposal.id,
            'unsignedTransactionHash': proposal.transaction_hash
        })
   
class TransactionProposalStatusView(APIView):

    def get_transaction_proposal(self, proposal_identifier):
        if proposal_identifier.isdigit():
            return get_object_or_404(MultisigTransactionProposal, id=int(proposal_identifier))
        return get_object_or_404(MultisigTransactionProposal, transaction_hash=proposal_identifier)
    
    def get(self, request, proposal_identifier):
        proposal = self.get_transaction_proposal(proposal_identifier)
        proposal_serializer = MultisigTransactionProposalSerializer(proposal, many=False)
        wallet_serializer = MultisigWalletSerializer(proposal.wallet, many=False)
        signing_progress_resp = js_client.get_signing_progress(proposal_serializer.data, wallet_serializer.data) 
        signing_progress_resp = signing_progress_resp.json()
        response_data = {
            'signingProgress': signing_progress_resp.get('signingProgress'),
            'broadcastStatus': proposal.broadcast_status,
            'transactionProposal': proposal.id,
            'wallet': proposal.wallet.id
        }
        return Response(response_data)
