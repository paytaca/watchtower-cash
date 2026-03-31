import logging
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from main.models import Transaction, TransactionBroadcast
from multisig import js_client
from multisig.auth.permission import IsCosigner, IsProposalCoordinator, ProposalCoordinatorHasValidSignature
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import models
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.db.models import Q
from main.tasks import NODE

from multisig.models.transaction import (
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


def should_include_deleted(request):
    return str(request.query_params.get("include_deleted")).lower() in ("1", "true")


def get_status_filter(request, default=Proposal.Status.PENDING):
    return request.query_params.get("status", default)


def get_proposal_queryset(request):
    queryset = Proposal.objects.all()
    if not should_include_deleted(request):
        queryset = queryset.filter(deleted_at__isnull=True)
    status_filter = get_status_filter(request)
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    return queryset


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
            return [IsCosigner(), ProposalCoordinatorHasValidSignature()]
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
            openapi.Parameter(
                "include_deleted",
                openapi.IN_QUERY,
                description="Include soft-deleted proposals (default: false)",
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                description="Filter by status (default: pending)",
                type=openapi.TYPE_STRING,
            ),
        ],
    )
    def get(self, request):

        queryset = get_proposal_queryset(request).prefetch_related("inputs")
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
        manual_parameters=[
            openapi.Parameter(
                "include_deleted",
                openapi.IN_QUERY,
                description="Include soft-deleted proposals (default: false)",
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                description="Filter by status (default: pending)",
                type=openapi.TYPE_STRING,
            ),
        ],
    )
    def get(self, request, wallet_identifier):
        wallet = get_wallet_by_identifier(wallet_identifier)
        queryset = (
            get_proposal_queryset(request)
            .prefetch_related("inputs")
            .filter(
                wallet=wallet,
            )
        )
        serializer = ProposalSerializer(queryset, many=True)
        return Response(serializer.data)


class ProposalDetailView(APIView):
    def get_permissions(self):
        if (
            self.request.method == "DELETE"
            or self.request.method == "PUT"
            or self.request.method == "PATCH"
        ):
            return [IsProposalCoordinator()]
        return []

    def get_object(self, identifier, request):
        queryset = Proposal.objects.prefetch_related("inputs")
        if not should_include_deleted(request):
            queryset = queryset.filter(deleted_at__isnull=True)
        return get_proposal_by_identifier(identifier, queryset=queryset)

    @swagger_auto_schema(
        operation_description="Retrieve a proposal by id.",
        responses={status.HTTP_200_OK: ProposalSerializer},
        manual_parameters=[
            openapi.Parameter(
                "include_deleted",
                openapi.IN_QUERY,
                description="Include soft-deleted proposals (default: false)",
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                description="Filter by status (default: pending)",
                type=openapi.TYPE_STRING,
            ),
        ],
    )
    def get(self, request, proposal_identifier):
        proposal = self.get_object(proposal_identifier, request)
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
        proposal = self.get_object(proposal_identifier, request)
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
        proposal = self.get_object(proposal_identifier, request)
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
        proposal = self.get_object(proposal_identifier, request)
        proposal.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProposalCoordinatorDetailView(APIView):
    def get_object(self, identifier, request):
        queryset = Proposal.objects.all()
        if not should_include_deleted(request):
            queryset = queryset.filter(deleted_at__isnull=True)
        return get_proposal_by_identifier(identifier, queryset=queryset)

    @swagger_auto_schema(
        operation_description="Retrieve a proposal coordinator by proposal's identifier.",
        responses={status.HTTP_200_OK: ProposalCoordinatorSerializer},
        manual_parameters=[
            openapi.Parameter(
                "include_deleted",
                openapi.IN_QUERY,
                description="Include soft-deleted proposals (default: false)",
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                description="Filter by status (default: pending)",
                type=openapi.TYPE_STRING,
            ),
        ],
    )
    def get(self, request, proposal_identifier):
        proposal = self.get_object(proposal_identifier, request)
        serializer = ProposalCoordinatorSerializer(proposal)
        return Response(serializer.data)


class ProposalInputListView(APIView):
    @swagger_auto_schema(
        operation_description="Read-only list of inputs for a proposal. Inputs are set at proposal creation only. Identifier is proposal id or unsigned_transaction_hash.",
        responses={status.HTTP_200_OK: InputSerializer(many=True)},
        manual_parameters=[
            openapi.Parameter(
                "include_deleted",
                openapi.IN_QUERY,
                description="Include soft-deleted proposals (default: false)",
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                description="Filter by status (default: pending)",
                type=openapi.TYPE_STRING,
            ),
        ],
    )
    def get(self, request, proposal_identifier):
        queryset = Proposal.objects.prefetch_related("inputs")
        if not should_include_deleted(request):
            queryset = queryset.filter(deleted_at__isnull=True)
        proposal = get_proposal_by_identifier(proposal_identifier, queryset)
        serializer = InputSerializer(proposal.inputs.all(), many=True)
        return Response(serializer.data)


class ProposalStatusView(APIView):
    """
    Returns the broadcast status and current spend status of inputs for a proposal.
    """

    @swagger_auto_schema(
        operation_description="Returns the broadcast status and current spend status of inputs for a proposal.",
        responses={status.HTTP_200_OK: openapi.Response(description="Status info")},
        manual_parameters=[
            openapi.Parameter(
                "include_deleted",
                openapi.IN_QUERY,
                description="Include soft-deleted proposals (default: false)",
                type=openapi.TYPE_BOOLEAN,
            ),
        ],
    )
    def get(self, request, proposal_identifier):

        queryset = Proposal.objects.all()
        if not should_include_deleted(request):
            queryset = queryset.filter(deleted_at__isnull=True)
        proposal = get_proposal_by_identifier(proposal_identifier, queryset)
        current_status = proposal.status
        new_status = current_status
        response_data = {
            "proposal_id": proposal.id,
            "proposal_unsigned_transaction_hash": proposal.unsigned_transaction_hash,
            "status": current_status,
            "inputs": [],
        }

        psbts = list(proposal.psbts.values_list("content", flat=True))
        signing_progress = proposal.signing_progress
        if len(psbts) > 0:
            combine_request = js_client.combine_psbts([proposal.combined_psbt, *psbts])
            combine_request.raise_for_status()
            combine_result = combine_request.json()
            LOGGER.info(f"combine result {combine_result}")
            signing_progress = combine_result.get("signingProgress", {})
            signing_progress = signing_progress.get("signingProgress")
        if signing_progress != proposal.signing_progress:
            response_data["signingProgress"] = signing_progress
            proposal.signing_progress = signing_progress
            proposal.save(update_fields=["signing_progress"])

        for inp in proposal.inputs.all():

            spending_tx = Transaction.objects.filter(
                txid=inp.outpoint_transaction_hash, 
                index=inp.outpoint_index
            ).first()
            
            spending_txid = None

            if spending_tx:
                spending_txid = spending_tx.spending_txid

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
                new_status = Proposal.Status.BROADCAST_INITIATED
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

            if new_status == Proposal.Status.BROADCAST_INITIATED:
                    transaction_broadcast = TransactionBroadcast.objects.filter(
                        txid=spending_txid
                    ).first()
                    if transaction_broadcast:
                        proposal.on_premise_transaction_broadcast = (
                            transaction_broadcast
                        )
                        proposal.save(
                            update_fields=["on_premise_transaction_broadcast"]
                        )

                    if (
                        not transaction_broadcast
                        and new_status == Proposal.Status.BROADCAST_INITIATED
                    ):
                        proposal.off_premise_transaction_broadcast = spending_txid
                        proposal.save(
                            update_fields=["off_premise_transaction_broadcast"]
                        )

                    response_data["txid"] = spending_txid

            response_data["status"] = new_status
            response_data["wallet"] = proposal.wallet.id
            response_data["inputs"].append(
                {
                    "outpoint_transaction_hash": inp.outpoint_transaction_hash,
                    "outpoint_index": inp.outpoint_index,
                    "spending_txid": spending_txid,
                }
            )

        return Response(response_data, status=status.HTTP_200_OK)


class PsbtListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsCosigner()]
        return []

    @swagger_auto_schema(
        operation_description="List signing submissions for a proposal. Identifier is proposal id or unsigned_transaction_hash.",
        responses={status.HTTP_200_OK: PsbtSerializer(many=True)},
        manual_parameters=[
            openapi.Parameter(
                "include_deleted",
                openapi.IN_QUERY,
                description="Include soft-deleted proposals (default: false)",
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                description="Filter by status (default: pending)",
                type=openapi.TYPE_STRING,
            ),
        ],
    )
    def get(self, request, proposal_identifier):
        proposal = get_proposal_by_identifier(
            proposal_identifier, get_proposal_queryset(request)
        )
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
        signer = getattr(request, "signer", None)
        proposal = get_proposal_by_identifier(
            proposal_identifier, get_proposal_queryset(request)
        )
        serializer = PsbtSerializer(data=request.data, context={"submitted_by": signer})
        if serializer.is_valid():
            serializer.save(proposal=proposal)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProposalSignatureListView(APIView):
    """Read-only list of signatures for a proposal (all inputs' signatures)."""

    @swagger_auto_schema(
        operation_description="List signatures for a proposal. Identifier is proposal id or unsigned_transaction_hash. Read-only.",
        responses={status.HTTP_200_OK: SignatureSerializer(many=True)},
        manual_parameters=[
            openapi.Parameter(
                "include_deleted",
                openapi.IN_QUERY,
                description="Include soft-deleted proposals (default: false)",
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                description="Filter by status (default: pending)",
                type=openapi.TYPE_STRING,
            ),
        ],
    )
    def get(self, request, proposal_identifier):
        proposal = get_proposal_by_identifier(
            proposal_identifier, get_proposal_queryset(request)
        )
        queryset = Signature.objects.filter(
            input__proposal_id=proposal.pk
        ).select_related("input")
        serializer = SignatureSerializer(queryset, many=True)
        return Response(serializer.data)


class ProposalSignatureDetailView(APIView):
    """Read-only detail of a single signature scoped to a proposal."""

    def get_object(self, proposal_identifier, pk, request):
        proposal = get_proposal_by_identifier(
            proposal_identifier, get_proposal_queryset(request)
        )
        return get_object_or_404(
            Signature.objects.select_related("input"),
            pk=pk,
            input__proposal_id=proposal.pk,
        )

    @swagger_auto_schema(
        operation_description="Retrieve a signature by id. Identifier is proposal id or unsigned_transaction_hash. Read-only.",
        responses={status.HTTP_200_OK: SignatureSerializer},
        manual_parameters=[
            openapi.Parameter(
                "include_deleted",
                openapi.IN_QUERY,
                description="Include soft-deleted proposals (default: false)",
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                description="Filter by status (default: pending)",
                type=openapi.TYPE_STRING,
            ),
        ],
    )
    def get(self, request, proposal_identifier, pk):
        signature = self.get_object(proposal_identifier, pk, request)
        serializer = SignatureSerializer(signature)
        return Response(serializer.data)


class SignatureBySignerIdentifierList(APIView):
    """Read-only list of signatures for inputs that have BIP32 derivation with the given master_fingerprint or public_key as identifier."""

    @swagger_auto_schema(
        operation_description="List signatures for inputs whose BIP32 derivation has this master fingerprint. Returns signature, publicKey, input, bip32Derivation. Read-only.",
        responses={status.HTTP_200_OK: SignatureWithBip32Serializer(many=True)},
        manual_parameters=[
            openapi.Parameter(
                "include_deleted",
                openapi.IN_QUERY,
                description="Include soft-deleted proposals (default: false)",
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                description="Filter by status (default: pending)",
                type=openapi.TYPE_STRING,
            ),
        ],
    )
    def get_queryset(self, proposal_identifier, signature_identifier, request):

        queryset = Proposal.objects.all()
        if not should_include_deleted(request):
            queryset = queryset.filter(deleted_at__isnull=True)
        status_filter = get_status_filter(request)
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        if proposal_identifier.isdigit():
            queryset = queryset.filter(id=int(proposal_identifier))
        else:
            queryset = queryset.filter(unsigned_transaction_hash=proposal_identifier)

        base = (
            Signature.objects.filter(input__proposal__in=queryset)
            .select_related("input")
            .prefetch_related("input__bip32_derivation")
        )

        return base.filter(
            input__bip32_derivation__master_fingerprint=signature_identifier,
            public_key=models.F("input__bip32_derivation__public_key"),
        ).distinct()

    def get(self, request, proposal_identifier, signature_identifier):
        queryset = self.get_queryset(proposal_identifier, signature_identifier, request)
        serializer = SignatureWithBip32Serializer(queryset, many=True)
        return Response(serializer.data)
