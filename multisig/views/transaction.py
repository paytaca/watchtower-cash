import logging
import requests
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from multisig.auth.auth import PubKeySignatureMessageAuthentication
from multisig.models.coordinator import ServerIdentity
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import models
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.db.models import Q

from multisig.models.transaction import Bip32Derivation, Proposal, SigningSubmission, Signature
from multisig.models.wallet import MultisigWallet
from multisig.serializers.transaction import (
    ProposalSerializer,
    InputSerializer,
    SigningSubmissionSerializer,
    SignatureSerializer,
    SignatureWithBip32Serializer,
)

LOGGER = logging.getLogger(__name__)


def get_proposal_by_identifier(identifier, queryset=None):
    """Resolve Proposal by id (if identifier is numeric) or unsigned_transaction_hash."""
    if queryset is None:
        queryset = Proposal.objects.all()
    if identifier.isdigit():
        return get_object_or_404(queryset, pk=int(identifier))
    return get_object_or_404(queryset, unsigned_transaction_hash=identifier)


def get_wallet_by_identifier(identifier, queryset=None):
    """Resolve MultisigWallet by id (if identifier is numeric), wallet_hash, or wallet_descriptor_id."""
    if queryset is None:
        queryset = MultisigWallet.objects.all()
    if identifier.isdigit():
        return get_object_or_404(queryset, pk=int(identifier))
    wallet = queryset.filter(
        Q(wallet_hash=identifier) | Q(wallet_descriptor_id=identifier)
    ).first()
    if wallet is None:
        raise Http404("No wallet matches the given identifier.")
    return wallet


class ProposalListCreateView(APIView):

    def get_authenticators(self):
        if self.request.method == "POST":
            return [PubKeySignatureMessageAuthentication()]
        return []
    
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
        coordinator = ServerIdentity.objects.filter(public_key=request.headers.get('X-Auth-PubKey')).first()
        if not coordinator:
                return Response({'error': 'Coordinator needs server identity'}, status=status.HTTP_400_BAD_REQUEST)
        
        LOGGER.info(coordinator)
        serializer = ProposalSerializer(data=request.data, context={'coordinator': coordinator})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class WalletProposalListView(APIView):
    """Read-only list of proposals for a wallet. Identifier is wallet id, wallet_hash, or wallet_descriptor_id."""

    @swagger_auto_schema(
        operation_description="List proposals for a wallet. Identifier is wallet id (numeric), wallet_hash, or wallet_descriptor_id.",
        responses={status.HTTP_200_OK: ProposalSerializer(many=True)},
    )
    def get(self, request, identifier):
        wallet = get_wallet_by_identifier(identifier)
        queryset = Proposal.objects.prefetch_related('inputs').filter(wallet=wallet)
        serializer = ProposalSerializer(queryset, many=True)
        return Response(serializer.data)


class ProposalDetailView(APIView):

    def get_object(self, identifier):
        return get_proposal_by_identifier(
            identifier,
            queryset=Proposal.objects.prefetch_related('inputs', 'signing_submissions'),
        )

    @swagger_auto_schema(
        operation_description="Retrieve a proposal by id.",
        responses={status.HTTP_200_OK: ProposalSerializer},
    )
    def get(self, request, identifier):
        proposal = self.get_object(identifier)
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
    def put(self, request, identifier):
        proposal = self.get_object(identifier)
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
    def patch(self, request, identifier):
        proposal = self.get_object(identifier)
        serializer = ProposalSerializer(proposal, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Delete a proposal.",
        responses={status.HTTP_204_NO_CONTENT: openapi.Response(description="No content")},
    )
    def delete(self, request, identifier):
        proposal = self.get_object(identifier)
        proposal.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProposalInputListView(APIView):
    @swagger_auto_schema(
        operation_description="Read-only list of inputs for a proposal. Inputs are set at proposal creation only. Identifier is proposal id or unsigned_transaction_hash.",
        responses={status.HTTP_200_OK: InputSerializer(many=True)},
    )
    def get(self, request, identifier):
        proposal = get_proposal_by_identifier(identifier, Proposal.objects.prefetch_related('inputs'))
        serializer = InputSerializer(proposal.inputs.all(), many=True)
        return Response(serializer.data)



class ProposalStatusView(APIView):
    """
    Returns the broadcast status and current spend status of inputs for a proposal.
    """
    def get(self, request, identifier):
        proposal = get_object_or_404(
            Proposal,
            pk=identifier if str(identifier).isdigit() else None,
            unsigned_transaction_hash=None if str(identifier).isdigit() else identifier
        )

        response_data = {
            "broadcast_status": proposal.broadcast_status,
            "inputs": [],
            "all_inputs_spent": None
        }
        any_spent = False
        all_spent = True
        checked_any = False

        for inp in proposal.inputs.all():
            checked_any = True
            txid = inp.outpoint_transaction_hash
            vout = inp.outpoint_index
            ## TODO: use the Transaction table in prod, this is for local testing only
            url = f"https://watchtower.cash/api/transactions/outputs/?txid={txid}"
            spent = None
            spending_txid = None
            try:
                api_resp = requests.get(url, timeout=10)
                data = api_resp.json()
                for result in data.get("results", []):
                    if result.get("txid") == txid and result.get("index") == vout:
                        spent = result.get("spent", None)
                        spending_txid = result.get("spending_txid", "")
                        if spent and spending_txid:
                            inp.spent_on_transaction = spending_txid
                            inp.save(update_fields=['spent_on_transaction'])
                            # TODO: mark proposal as conflicted if the spending tx unsigned transaction hash isn't the same as this proposal's unsigned transaction hash
                        break
            except Exception as e:
                spent = None  

            response_data["inputs"].append({
                "outpoint_transaction_hash": txid,
                "outpoint_index": vout,
                "spent": spent,
                "spending_txid": spending_txid,
            })
            if spent is None:
                all_spent = None
            elif spent:
                any_spent = True
            else:
                all_spent = False

        if not checked_any:
            all_spent = None  

        response_data["any_input_spent"] = any_spent
        response_data["all_inputs_spent"] = all_spent

        return Response(response_data, status=status.HTTP_200_OK)


class ProposalSigningSubmissionListCreateView(APIView):
    @swagger_auto_schema(
        operation_description="List signing submissions for a proposal. Identifier is proposal id or unsigned_transaction_hash.",
        responses={status.HTTP_200_OK: SigningSubmissionSerializer(many=True)},
    )
    def get(self, request, identifier):
        proposal = get_proposal_by_identifier(identifier)
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
    def post(self, request, identifier):
        proposal = get_proposal_by_identifier(identifier)
        serializer = SigningSubmissionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(proposal=proposal)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProposalSigningSubmissionDetailView(APIView):
    def get_object(self, identifier, pk):
        proposal = get_proposal_by_identifier(identifier)
        return get_object_or_404(SigningSubmission, proposal_id=proposal.pk, pk=pk)

    @swagger_auto_schema(
        operation_description="Retrieve a signing submission by id. Identifier is proposal id or unsigned_transaction_hash.",
        responses={status.HTTP_200_OK: SigningSubmissionSerializer},
    )
    def get(self, request, identifier, pk):
        submission = self.get_object(identifier, pk)
        serializer = SigningSubmissionSerializer(submission)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Delete a signing submission.",
        responses={status.HTTP_204_NO_CONTENT: openapi.Response(description="No content")},
    )
    def delete(self, request, identifier, pk):
        submission = self.get_object(identifier, pk)
        submission.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProposalSignatureListView(APIView):
    """Read-only list of signatures for a proposal (all inputs' signatures)."""

    @swagger_auto_schema(
        operation_description="List signatures for a proposal. Identifier is proposal id or unsigned_transaction_hash. Read-only.",
        responses={status.HTTP_200_OK: SignatureSerializer(many=True)},
    )
    def get(self, request, identifier):
        proposal = get_proposal_by_identifier(identifier)
        queryset = Signature.objects.filter(input__proposal_id=proposal.pk).select_related('input')
        serializer = SignatureSerializer(queryset, many=True)
        return Response(serializer.data)


class ProposalSignatureDetailView(APIView):
    """Read-only detail of a single signature scoped to a proposal."""

    def get_object(self, identifier, pk):
        proposal = get_proposal_by_identifier(identifier)
        return get_object_or_404(
            Signature.objects.select_related('input'),
            pk=pk,
            input__proposal_id=proposal.pk,
        )

    @swagger_auto_schema(
        operation_description="Retrieve a signature by id. Identifier is proposal id or unsigned_transaction_hash. Read-only.",
        responses={status.HTTP_200_OK: SignatureSerializer},
    )
    def get(self, request, identifier, pk):
        signature = self.get_object(identifier, pk)
        serializer = SignatureSerializer(signature)
        return Response(serializer.data)


class SignatureBySignerIdentifierList(APIView):
    """Read-only list of signatures for inputs that have BIP32 derivation with the given master_fingerprint or public_key as identifier."""

    @swagger_auto_schema(
        operation_description="List signatures for inputs whose BIP32 derivation has this master fingerprint. Returns signature, publicKey, input, bip32Derivation. Read-only.",
        responses={status.HTTP_200_OK: SignatureWithBip32Serializer(many=True)},
    )
    def get_queryset(self, proposal_identifier, identifier):

        if proposal_identifier.isdigit():
            base = (
                Signature.objects.filter(input__proposal__id=int(proposal_identifier))
                .select_related('input')
                .prefetch_related('input__bip32_derivation')
            )
        else:
            base = (
                Signature.objects.filter(input__proposal__unsigned_transaction_hash=proposal_identifier)
                .select_related('input')
                .prefetch_related('input__bip32_derivation')
            )


        return base.filter(
                input__bip32_derivation__master_fingerprint=identifier,
                public_key=models.F('input__bip32_derivation__public_key')
            ).distinct()

        

    def get(self, request, proposal_identifier, identifier):
        # Ensure proposal exists (404 if not)
        get_object_or_404(Proposal, unsigned_transaction_hash=proposal_identifier)
        queryset = self.get_queryset(proposal_identifier, identifier)
        serializer = SignatureWithBip32Serializer(queryset, many=True)
        return Response(serializer.data)
