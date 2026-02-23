import logging
import hashlib
from multisig.auth.auth import parse_x_signature_header
from multisig.js_client import verify_signature
from multisig.utils import derive_pubkey_from_xpub
from multisig.models.wallet import Signer
from rest_framework import permissions
from rest_framework.exceptions import ValidationError, AuthenticationFailed
from django.conf import settings

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

        wallet_id = request.data.get("wallet")
        if not wallet_id:
            return False

        auth_public_key = request.headers.get("X-Auth-Cosigner-Auth-PubKey", "")
        message = request.headers.get("X-Auth-Cosigner-Auth-Message", "")
        signature = request.headers.get("X-Auth-Cosigner-Auth-Signature", "")

        if not auth_public_key or not message or not signature:
            return False
        
        signer = (
            Signer.objects.filter(
                wallet_id=wallet_id, auth_public_key=auth_public_key
            )
            .first()
        )

        if not signer:
            return False

        signature = parse_x_signature_header(signature)
        sig_verification_response = verify_signature(
            message, auth_public_key, signature
        )
        sig_verification_result = sig_verification_response.json()

        if sig_verification_result.get("success", False):
            request.signer = signer
            return True

        return False
