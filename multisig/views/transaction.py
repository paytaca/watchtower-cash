import logging

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from multisig.models.transaction import Proposal, SigningSubmission, Signature
from multisig.serializers.transaction import (
    ProposalSerializer,
    InputSerializer,
    SigningSubmissionSerializer,
    SignatureSerializer,
    SignatureWithBip32Serializer,
)

LOGGER = logging.getLogger(__name__)

class ProposalListCreateView(APIView):
    @swagger_auto_schema(
        operation_description="List proposals. Optionally filter by wallet id.",
        responses={status.HTTP_200_OK: ProposalSerializer(many=True)},
        manual_parameters=[
            openapi.Parameter('wallet', openapi.IN_QUERY, description="Filter by wallet id", type=openapi.TYPE_INTEGER),
        ],
    )
    def get(self, request):
        queryset = Proposal.objects.prefetch_related('inputs').all()
        wallet_id = request.query_params.get('wallet')
        if wallet_id:
            queryset = queryset.filter(wallet_id=wallet_id)
        serializer = ProposalSerializer(queryset, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Create a new proposal. Request body: { proposal: string, proposalFormat: string }.",
        request_body=ProposalSerializer,
        responses={
            status.HTTP_201_CREATED: ProposalSerializer,
            status.HTTP_400_BAD_REQUEST: openapi.Response(description="Validation error"),
        },
    )
    def post(self, request):
        serializer = ProposalSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProposalDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(Proposal.objects.prefetch_related('inputs', 'signing_submissions'), pk=pk)

    @swagger_auto_schema(
        operation_description="Retrieve a proposal by id.",
        responses={status.HTTP_200_OK: ProposalSerializer},
    )
    def get(self, request, pk):
        proposal = self.get_object(pk)
        serializer = ProposalSerializer(proposal)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Full update of a proposal.",
        request_body=ProposalSerializer,
        responses={
            status.HTTP_200_OK: ProposalSerializer,
            status.HTTP_400_BAD_REQUEST: openapi.Response(description="Validation error"),
        },
    )
    def put(self, request, pk):
        proposal = self.get_object(pk)
        serializer = ProposalSerializer(proposal, data=request.data, partial=False)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Partial update of a proposal.",
        request_body=ProposalSerializer,
        responses={
            status.HTTP_200_OK: ProposalSerializer,
            status.HTTP_400_BAD_REQUEST: openapi.Response(description="Validation error"),
        },
    )
    def patch(self, request, pk):
        proposal = self.get_object(pk)
        serializer = ProposalSerializer(proposal, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Delete a proposal.",
        responses={status.HTTP_204_NO_CONTENT: openapi.Response(description="No content")},
    )
    def delete(self, request, pk):
        proposal = self.get_object(pk)
        proposal.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProposalInputListView(APIView):
    @swagger_auto_schema(
        operation_description="Read-only list of inputs for a proposal. Inputs are set at proposal creation only.",
        responses={status.HTTP_200_OK: InputSerializer(many=True)},
    )
    def get(self, request, proposal_pk):
        proposal = get_object_or_404(Proposal.objects.prefetch_related('inputs'), pk=proposal_pk)
        serializer = InputSerializer(proposal.inputs.all(), many=True)
        return Response(serializer.data)


class ProposalSigningSubmissionListCreateView(APIView):
    def get_proposal(self, pk):
        return get_object_or_404(Proposal, pk=pk)

    @swagger_auto_schema(
        operation_description="List signing submissions for a proposal.",
        responses={status.HTTP_200_OK: SigningSubmissionSerializer(many=True)},
    )
    def get(self, request, proposal_pk):
        proposal = self.get_proposal(proposal_pk)
        submissions = proposal.signing_submissions.all()
        serializer = SigningSubmissionSerializer(submissions, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Submit a signing payload for a proposal.",
        request_body=SigningSubmissionSerializer,
        responses={
            status.HTTP_201_CREATED: SigningSubmissionSerializer,
            status.HTTP_400_BAD_REQUEST: openapi.Response(description="Validation error"),
        },
    )
    def post(self, request, proposal_pk):
        proposal = self.get_proposal(proposal_pk)
        serializer = SigningSubmissionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(proposal=proposal)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProposalSigningSubmissionDetailView(APIView):
    def get_object(self, proposal_pk, pk):
        return get_object_or_404(SigningSubmission, proposal_id=proposal_pk, pk=pk)

    @swagger_auto_schema(
        operation_description="Retrieve a signing submission by id.",
        responses={status.HTTP_200_OK: SigningSubmissionSerializer},
    )
    def get(self, request, proposal_pk, pk):
        submission = self.get_object(proposal_pk, pk)
        serializer = SigningSubmissionSerializer(submission)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Delete a signing submission.",
        responses={status.HTTP_204_NO_CONTENT: openapi.Response(description="No content")},
    )
    def delete(self, request, proposal_pk, pk):
        submission = self.get_object(proposal_pk, pk)
        submission.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProposalSignatureListView(APIView):
    """Read-only list of signatures for a proposal (all inputs' signatures)."""

    @swagger_auto_schema(
        operation_description="List signatures for a proposal. Read-only.",
        responses={status.HTTP_200_OK: SignatureSerializer(many=True)},
    )
    def get(self, request, proposal_pk):
        get_object_or_404(Proposal, pk=proposal_pk)
        queryset = Signature.objects.filter(input__proposal_id=proposal_pk).select_related('input')
        serializer = SignatureSerializer(queryset, many=True)
        return Response(serializer.data)


class ProposalSignatureDetailView(APIView):
    """Read-only detail of a single signature scoped to a proposal."""

    def get_object(self, proposal_pk, pk):
        return get_object_or_404(
            Signature.objects.select_related('input'),
            pk=pk,
            input__proposal_id=proposal_pk,
        )

    @swagger_auto_schema(
        operation_description="Retrieve a signature by id. Read-only.",
        responses={status.HTTP_200_OK: SignatureSerializer},
    )
    def get(self, request, proposal_pk, pk):
        signature = self.get_object(proposal_pk, pk)
        serializer = SignatureSerializer(signature)
        return Response(serializer.data)


class SignatureBySignerIdentifierList(APIView):
    """Read-only list of signatures for inputs that have BIP32 derivation with the given master_fingerprint or public_key as identifier."""

    @swagger_auto_schema(
        operation_description="List signatures for inputs whose BIP32 derivation has this master fingerprint. Returns signature, publicKey, input, bip32Derivation. Read-only.",
        responses={status.HTTP_200_OK: SignatureWithBip32Serializer(many=True)},
    )
    def get_queryset(self, proposal_unsigned_transaction_hash, identifier):
        base = (
            Signature.objects.filter(input__proposal__unsigned_transaction_hash=proposal_unsigned_transaction_hash)
            .select_related('input')
            .prefetch_related('input__bip32_derivation')
        )

        if len(identifier) == 8:
            return base.filter(input__bip32_derivation__master_fingerprint=identifier).distinct()

        return base.filter(input__bip32_derivation__public_key=identifier).distinct()

    def get(self, request, proposal_unsigned_transaction_hash, identifier):
        # Ensure proposal exists (404 if not)
        get_object_or_404(Proposal, unsigned_transaction_hash=proposal_unsigned_transaction_hash)
        queryset = self.get_queryset(proposal_unsigned_transaction_hash, identifier)
        serializer = SignatureWithBip32Serializer(queryset, many=True)
        return Response(serializer.data)
