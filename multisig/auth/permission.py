import logging
import hashlib
from multisig.auth.auth import parse_x_signature_header
from multisig import js_client
from multisig.js_client import verify_signature
from multisig.utils import derive_pubkey_from_xpub, generate_transaction_hash
from multisig.models.wallet import Signer
from multisig.models.transaction import Proposal
from multisig.models.auth import ServerIdentity
from multisig.models.wallet import MultisigWallet
from rest_framework import permissions
from rest_framework.exceptions import (
    ValidationError,
    AuthenticationFailed,
    PermissionDenied,
)
from django.conf import settings
from django.db.models import Q

LOGGER = logging.getLogger(__name__)


class IsCosigner(permissions.BasePermission):
    """
    Permission class that verifies a cosigner using their auth public key.

    Expected headers:
            - X-Auth-Cosigner-Auth-Public-Key: The raw public key derived at path 999/0
        - X-Auth-Cosigner-Auth-Message: The message that was signed
        - X-Auth-Cosigner-Auth-Signature: The signature in format 'schnorr=<sig>;der=<sig>'

    The cosigner_auth_public_key is double-SHA256 hashed and compared against
    the stored hash in the Signer model to identify the cosigner.

    On successful authentication, attaches the matched Signer to request.signer.
    """

    def has_permission(self, request, view):
        if not getattr(settings, "MULTISIG", {}).get("ENABLE_AUTH", False):
            return True

        wallet_id = request.data.get("wallet") or request.query_params.get("wallet_id")
        if not wallet_id:
            raise PermissionDenied("Invalid wallet identifier.")

        auth_public_key = request.headers.get("X-Auth-Cosigner-Auth-PubKey", "")
        message = request.headers.get("X-Auth-Cosigner-Auth-Message", "")
        signature = request.headers.get("X-Auth-Cosigner-Auth-Signature", "")

        if not auth_public_key or not message or not signature:
            raise PermissionDenied("Missing authentication headers.")

        signer = Signer.objects.filter(
            wallet_id=wallet_id, auth_public_key=auth_public_key
        ).first()

        if not signer:
            raise PermissionDenied("User is not a cosigner of the proposal.")

        signature = parse_x_signature_header(signature)

        sig_verification_response = verify_signature(
            message, auth_public_key, signature
        )
        sig_verification_result = sig_verification_response.json()

        if not sig_verification_result.get("success", False):
            raise PermissionDenied("Access denied, Invalid Signature.")

        request.signer = signer

        return True


class IsProposalCoordinator(IsCosigner):
    """
    Permission class that allows action only if the user passes IsCosigner
    and is the coordinator of the Proposal identified by its proposal_identifier.
    """

    def has_permission(self, request, view):
        super().has_permission(request, view)
        signer = getattr(request, "signer")
        proposal_identifier = request.resolver_match.kwargs.get(
            "proposal_identifier", None
        )
        if not proposal_identifier:
            raise PermissionDenied("Invalid proposal identifier.")
        queryset = Proposal.objects.all()
        if proposal_identifier.isdigit():
            proposal = queryset.filter(pk=int(proposal_identifier)).first()
        else:
            proposal = queryset.filter(
                unsigned_transaction_hash=proposal_identifier
            ).first()
        if not proposal:
            raise PermissionDenied("User non existing proposal.")
        if proposal.coordinator.id != signer.id:
            raise PermissionDenied("User is not the coordinator of this proposal.")

        request.proposal = proposal
        return True


class ProposalCoordinatorHasValidSignature(IsCosigner):
    """
    Permission class that verifies the coordinator_proposal_signature before creating a Proposal.

    Inherits from IsCosigner to authenticate the signer first.
    Verifies that the coordinator_proposal_signature from request body is valid by checking it against
    the signer's auth_public_key, with the unsigned_transaction_hash (computed from the proposal) as the message.
    """

    def has_permission(self, request, view):
        super().has_permission(request, view)

        if not getattr(settings, "MULTISIG", {}).get("ENABLE_AUTH", False):
            return True

        signer = getattr(request, "signer")

        coordinator_proposal_signature = request.data.get(
            "coordinatorProposalSignature"
        )
        if not coordinator_proposal_signature:
            raise PermissionDenied("Missing coordinator proposal signature.")

        if not signer.auth_public_key:
            raise PermissionDenied("Signer has no auth public key.")

        proposal_data = request.data.get("proposal")
        if not proposal_data:
            raise PermissionDenied("Missing proposal data.")

        proposal_format = request.data.get("proposal_format") or "psbt"
        if proposal_format == "psbt":
            decode_response = js_client.decode_psbt(proposal_data)
            if not decode_response.ok:
                raise PermissionDenied("Invalid proposal data.")
            decoded = decode_response.json()
            unsigned_transaction_hex = decoded.get("unsignedTransactionHex")
            if not unsigned_transaction_hex:
                raise PermissionDenied(
                    "Could not extract unsigned transaction from proposal."
                )
        else:
            raise PermissionDenied("Unsupported proposal format.")

        unsigned_transaction_hash = generate_transaction_hash(unsigned_transaction_hex)

        signature_scheme = (
            request.data.get("coordinatorProposalSignatureScheme") or "schnorr"
        )
        signature = {
            "schnorr": coordinator_proposal_signature
            if signature_scheme == "schnorr"
            else "",
            "der": coordinator_proposal_signature
            if signature_scheme == "ecdsa"
            else "",
        }
        sig_verification_response = verify_signature(
            unsigned_transaction_hash,
            signer.auth_public_key,
            signature,
            'hex'
        )
        sig_verification_result = sig_verification_response.json()
        if not sig_verification_result.get("success", False):
            raise PermissionDenied("Invalid coordinator proposal signature.")
        return True
