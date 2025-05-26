from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotFound
from multisig.models import MultisigTransactionProposal, Signer
from multisig.serializers import (
    MultisigTransactionProposalSerializer,
    SignatureSerializer
)
from multisig.models.wallet import MultisigWallet

class MultisigTransactionProposalListCreateView(APIView):
    def get(self, request):
        proposals = MultisigTransactionProposal.objects.all()
        serializer = MultisigTransactionProposalSerializer(proposals, many=True)
        return Response(serializer.data)

    def post(self, request, wallet_pk):
        multisig_wallet = get_object_or_404(MultisigWallet, pk=wallet_pk)

        serializer = MultisigTransactionProposalSerializer(data=request.data)
        if serializer.is_valid():
            proposal = serializer.save(wallet=multisig_wallet)
            return Response(MultisigTransactionProposalSerializer(proposal).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MultisigTransactionProposalDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(MultisigTransactionProposal, pk=pk)

    def get(self, request, pk):
        proposal = self.get_object(pk)
        serializer = MultisigTransactionProposalSerializer(proposal)
        return Response(serializer.data)

    def delete(self, request, pk):
        proposal = self.get_object(pk)
        proposal.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SignatureAddView(APIView):
    def post(self, request, proposal_id, signer_id):
        try:
            proposal = MultisigTransactionProposal.objects.get(id=proposal_id)
            signer = get_object_or_404(Signer, id=signer_id)
        except MultisigTransactionProposal.DoesNotExist:
            raise NotFound(f"MultisigTransactionProposal with id {proposal_id} not found.")
        except MultisigTransactionProposal.DoesNotExist:
            raise NotFound(f"Signer with id {signer_id} not found.")
        
        data = request.data.copy()
        
        for input_index, signature_key_value in data:
            signature_model_data = {
                'transaction_proposal': proposal.id,
                'signer': signer.id,
                'input_index': input_index
            }
            for key, value in signature_key_value:
                signature_model_data['signature_key'] = key
                signature_model_data['signature_value'] = value
                serializer = SignatureSerializer(data=signature_model_data)
                if serializer.is_valid():
                    signature = serializer.save()

            return Response(SignatureSerializer(signature).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
