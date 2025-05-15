from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotFound
from multisig.models import MultisigTransactionProposal, Signer
from multisig.serializers import (
    MultisigTransactionProposalSerializer,
    SignatureSerializer
)
from django.shortcuts import get_object_or_404


class MultisigTransactionProposalListCreateView(APIView):
    def get(self, request):
        proposals = MultisigTransactionProposal.objects.all()
        serializer = MultisigTransactionProposalSerializer(proposals, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = MultisigTransactionProposalSerializer(data=request.data)
        if serializer.is_valid():
            proposal = serializer.save()
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
        data['transaction_proposal'] = proposal.id
        data['signer'] = signer.id
        serializer = SignatureSerializer(data=data)
        if serializer.is_valid():
            signature = serializer.save()
            return Response(SignatureSerializer(signature).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
