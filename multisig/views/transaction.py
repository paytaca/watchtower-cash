import logging
import requests
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from main.models import TransactionBroadcast
from multisig import js_client
from multisig.auth.auth import PubKeySignatureMessageAuthentication
from multisig.auth.permission import IsCosigner, IsProposalCoordinator
from multisig.models.auth import ServerIdentity
from rampp2p.utils import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import models
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.db.models import Q
from main.tasks import NODE

from multisig.models.transaction import (
    Bip32Derivation,
    Proposal,
    Signature,
)
from multisig.models.wallet import MultisigWallet
from multisig.serializers.transaction import (
    ProposalCoordinatorSerializer,
    ProposalSerializer,
    InputSerializer,
    PsbtSerializer,
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
    
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsCosigner()]
        return []

    @swagger_auto_schema(
        operation_description="List proposals. Optionally filter by wallet id.",
        responses={status.HTTP_200_OK: ProposalSerializer(many=True)},
        manual_parameters=[
            openapi.Parameter(
                "wallet",
                openapi.IN_QUERY,
                description="Filter by wallet id",
                type=openapi.TYPE_INTEGER,
            ),
        ],
    )
    def get(self, request):

        queryset = Proposal.objects.prefetch_related("inputs").all()
        wallet_id = request.query_params.get("wallet")
        if wallet_id:
            queryset = queryset.filter(wallet_id=wallet_id)
        serializer = ProposalSerializer(queryset, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Create a new proposal. Request body: { proposal: string, proposalFormat: string }.",
        request_body=ProposalSerializer,
        responses={
            status.HTTP_201_CREATED: ProposalSerializer,
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                description="Validation error"
            ),
        },
    )
    def post(self, request):
        signer = getattr(request, "signer", None)
        if not signer:
            return Response(
                {"error": "Signer not authenticated"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = ProposalSerializer(
            data=request.data, context={"coordinator": signer}
        )

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
    def get(self, request, wallet_identifier):
        wallet = get_wallet_by_identifier(wallet_identifier)
        show_deleted = str(request.query_params.get("include_deleted")).lower() in (
            "1",
            "true",
        )
        queryset = Proposal.objects.prefetch_related("inputs").filter(
            wallet=wallet,
            status=(
                request.query_params.get(
                    "status", Proposal.Status.PENDING
                )
            ),
        )

        if not show_deleted:
            queryset = queryset.filter(deleted_at__isnull=True)

        serializer = ProposalSerializer(queryset, many=True)
        return Response(serializer.data)


class ProposalDetailView(APIView):

    def get_permissions(self):
        if self.request.method == "DELETE" or self.request.method == "PUT" or self.request.method == "PATCH":
            return [IsProposalCoordinator()]
        return []

    def get_object(self, identifier):
        return get_proposal_by_identifier(
            identifier,
            queryset=Proposal.objects.prefetch_related("inputs").filter(deleted_at__isnull=True),
        )

    @swagger_auto_schema(
        operation_description="Retrieve a proposal by id.",
        responses={status.HTTP_200_OK: ProposalSerializer},
    )
    def get(self, request, proposal_identifier):
        proposal = self.get_object(proposal_identifier)
        serializer = ProposalSerializer(proposal)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Full update of a proposal.",
        request_body=ProposalSerializer,
        responses={
            status.HTTP_200_OK: ProposalSerializer,
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                description="Validation error"
            ),
        },
    )
    def put(self, request, proposal_identifier):
        proposal = self.get_object(proposal_identifier)
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
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                description="Validation error"
            ),
        },
    )
    def patch(self, request, proposal_identifier):
        proposal = self.get_object(proposal_identifier)
        serializer = ProposalSerializer(proposal, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Delete a proposal.",
        responses={
            status.HTTP_204_NO_CONTENT: openapi.Response(description="No content")
        },
    )
    def delete(self, request, proposal_identifier):
        proposal = self.get_object(proposal_identifier)
        proposal.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class ProposalCoordinatorDetailView(APIView):

    def get_object(self, identifier):
        return get_proposal_by_identifier(
            identifier,
            queryset=Proposal.objects.filter(deleted_at__isnull=True),
        )

    @swagger_auto_schema(
        operation_description="Retrieve a proposal coordinator by proposal's identifier.",
        responses={status.HTTP_200_OK: ProposalCoordinatorSerializer},
    )
    def get(self, request, proposal_identifier):
        proposal = self.get_object(proposal_identifier)
        serializer = ProposalCoordinatorSerializer(proposal)
        return Response(serializer.data)

class ProposalInputListView(APIView):
    @swagger_auto_schema(
        operation_description="Read-only list of inputs for a proposal. Inputs are set at proposal creation only. Identifier is proposal id or unsigned_transaction_hash.",
        responses={status.HTTP_200_OK: InputSerializer(many=True)},
    )
    def get(self, request, proposal_identifier):
        proposal = get_proposal_by_identifier(
            proposal_identifier, Proposal.objects.prefetch_related("inputs")
        )
        serializer = InputSerializer(proposal.inputs.all(), many=True)
        return Response(serializer.data)

class ProposalStatusView(APIView):
    """
    Returns the broadcast status and current spend status of inputs for a proposal.
    """

    def get(self, request, proposal_identifier):

        proposal = get_proposal_by_identifier(proposal_identifier)
        current_status = proposal.status
        response_data = {
            "proposal_id": proposal.id,
            "proposal_unsigned_transaction_hash": proposal.unsigned_transaction_hash,
            "status": current_status,
            "inputs": [],
        }

        for inp in proposal.inputs.all():
            ## TODO: use the Transaction table in prod, this is for local testing only
            url = f"https://watchtower.cash/api/transactions/outputs/?txid={inp.outpoint_transaction_hash}"

            spending_txid = None

            api_resp = requests.get(url, timeout=10)
            data = api_resp.json()
            for result in data.get("results", []):
                if result.get("txid") == inp.outpoint_transaction_hash and result.get("index") == inp.outpoint_index:
                    spending_txid = result.get("spending_txid", "")
                else: 
                    continue

                spending_transaction = None
                if spending_txid:
                    inp.spending_txid = spending_txid
                    inp.save(update_fields=["spending_txid"])
                    spending_transaction = NODE.BCH._get_raw_transaction(spending_txid)

                spending_transaction_unsigned_transaction_hash = None
                if spending_transaction:
                    get_unsigned_transaction_hash_resp = (
                        js_client.get_unsigned_transaction_hash(
                            spending_transaction["hex"]
                        )
                    )
                    spending_transaction_unsigned_transaction_hash = (
                        get_unsigned_transaction_hash_resp.json().get(
                            "unsigned_transaction_hash"
                        )
                    )


                if (
                    spending_transaction_unsigned_transaction_hash
                    and spending_transaction_unsigned_transaction_hash
                    == proposal.unsigned_transaction_hash
                ):
                    new_status = Proposal.Status.BROADCASTED
                elif (
                    spending_transaction_unsigned_transaction_hash
                    and spending_transaction_unsigned_transaction_hash
                    != proposal.unsigned_transaction_hash
                ):
                    new_status = Proposal.Status.CONFLICTED
                    inp.conflicting_proposal_identifier = (
                        spending_transaction_unsigned_transaction_hash
                    )

                if current_status != new_status:
                    proposal.status = new_status
                    proposal.save(update_fields=["status"])

                if new_status == Proposal.Status.BROADCASTED:
                    transaction_broadcast = TransactionBroadcast.objects.filter(
                        txid=spending_txid
                    )
                    if transaction_broadcast:
                        proposal.on_premise_transaction_broadcast = (
                            transaction_broadcast
                        )
                        proposal.save(
                            update_fields=["on_premise_transaction_broadcast"]
                        )

                    if (
                        not transaction_broadcast
                        and new_status
                        == Proposal.Status.BROADCASTED
                    ):
                        proposal.off_premise_transaction_broadcast = spending_txid
                        proposal.save(
                            update_fields=["off_premise_transaction_broadcast"]
                        )

                    response_data["txid"] = spending_txid

            response_data["inputs"].append(
                {
                    "outpoint_transaction_hash": inp.outpoint_transaction_hash,
                    "outpoint_index": inp.outpoint_index,
                    "spending_txid": spending_txid,
                }
            )

        return Response(response_data, status=status.HTTP_200_OK)


class PsbtListCreateView(APIView):
    @swagger_auto_schema(
        operation_description="List signing submissions for a proposal. Identifier is proposal id or unsigned_transaction_hash.",
        responses={status.HTTP_200_OK: PsbtSerializer(many=True)},
    )
    def get(self, request, proposal_identifier):
        proposal = get_proposal_by_identifier(proposal_identifier, Proposal.objects.filter(deleted_at__isnull=True))
        psbts = proposal.psbts.all()
        serializer = PsbtSerializer(psbts, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Submit a signing payload for a proposal.",
        request_body=PsbtSerializer,
        responses={
            status.HTTP_201_CREATED: PsbtSerializer,
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                description="Validation error"
            ),
        },
    )
    def post(self, request, proposal_identifier):
        proposal = get_proposal_by_identifier(proposal_identifier, Proposal.objects.filter(deleted_at__isnull=True))
        serializer = PsbtSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(proposal=proposal)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class ProposalSignatureListView(APIView):
    """Read-only list of signatures for a proposal (all inputs' signatures)."""

    @swagger_auto_schema(
        operation_description="List signatures for a proposal. Identifier is proposal id or unsigned_transaction_hash. Read-only.",
        responses={status.HTTP_200_OK: SignatureSerializer(many=True)},
    )
    def get(self, request, proposal_identifier):
        proposal = get_proposal_by_identifier(proposal_identifier, Proposal.objects.filter(deleted_at__isnull=True))
        queryset = Signature.objects.filter(
            input__proposal_id=proposal.pk
        ).select_related("input")
        serializer = SignatureSerializer(queryset, many=True)
        return Response(serializer.data)


class ProposalSignatureDetailView(APIView):
    """Read-only detail of a single signature scoped to a proposal."""

    def get_object(self, proposal_identifier, pk):
        proposal = get_proposal_by_identifier(proposal_identifier, Proposal.objects.filter(deleted_at__isnull=True))
        return get_object_or_404(
            Signature.objects.select_related("input"),
            pk=pk,
            input__proposal_id=proposal.pk,
        )

    @swagger_auto_schema(
        operation_description="Retrieve a signature by id. Identifier is proposal id or unsigned_transaction_hash. Read-only.",
        responses={status.HTTP_200_OK: SignatureSerializer},
    )
    def get(self, request, proposal_identifier, pk):
        signature = self.get_object(proposal_identifier, pk)
        serializer = SignatureSerializer(signature)
        return Response(serializer.data)


class SignatureBySignerIdentifierList(APIView):
    """Read-only list of signatures for inputs that have BIP32 derivation with the given master_fingerprint or public_key as identifier."""

    @swagger_auto_schema(
        operation_description="List signatures for inputs whose BIP32 derivation has this master fingerprint. Returns signature, publicKey, input, bip32Derivation. Read-only.",
        responses={status.HTTP_200_OK: SignatureWithBip32Serializer(many=True)},
    )
    def get_queryset(self, proposal_identifier, signature_identifier):

        if proposal_identifier.isdigit():
            base = (
                Signature.objects.filter(input__proposal__id=int(proposal_identifier))
                .select_related("input")
                .prefetch_related("input__bip32_derivation")
            )
        else:
            base = (
                Signature.objects.filter(
                    input__proposal__unsigned_transaction_hash=proposal_identifier
                )
                .select_related("input")
                .prefetch_related("input__bip32_derivation")
            )

        return base.filter(
            input__bip32_derivation__master_fingerprint=signature_identifier,
            public_key=models.F("input__bip32_derivation__public_key"),
        ).distinct()

    def get(self, request, proposal_identifier, signature_identifier):
        # Ensure proposal exists (404 if not)
        get_object_or_404(Proposal, unsigned_transaction_hash=proposal_identifier)
        queryset = self.get_queryset(proposal_identifier, signature_identifier)
        serializer = SignatureWithBip32Serializer(queryset, many=True)
        return Response(serializer.data)
