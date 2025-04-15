# multisig/decorators.py
from rest_framework.response import Response
from rest_framework import status
from functools import wraps
from .models import Signer
from .crypto_utils import verify_signature

def signer_required(view_func):
    @wraps(view_func)
    def _wrapped_view(self, request, wallet_id=None, *args, **kwargs):
        # Retrieve headers for signature verification
        xpub = request.headers.get("X-Xpub")
        signature = request.headers.get("X-Signature")
        message = request.headers.get("X-Message")
        algo = request.headers.get("X-Signature-Algo", "schnorr")  # Default to schnorr if not provided

        if not xpub or not signature or not message:
            return Response({"detail": "Missing auth headers"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Check if the signer exists in the wallet
            signer = Signer.objects.get(xpub=xpub, wallet_id=wallet_id)
        except Signer.DoesNotExist:
            return Response({"detail": "Signer not found in this wallet"}, status=status.HTTP_403_FORBIDDEN)

        # Verify the signature using the utility
        valid = verify_signature(message, signature, xpub, signer.derivation_path, algo)
        if not valid:
            return Response({"detail": "Signature verification failed"}, status=status.HTTP_403_FORBIDDEN)

        # Optionally attach the signer to the request if needed for later use
        request.signer = signer
        return view_func(self, request, wallet_id=wallet_id, *args, **kwargs)

    return _wrapped_view
