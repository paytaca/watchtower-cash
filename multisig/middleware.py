import logging
from django.http import JsonResponse
from django.conf import settings
from redis import Redis
from .crypto_utils import verify_signature, get_address_index
from .models import Signer

LOGGER = logging.getLogger(__name__)

nonce_cache = settings.REDISKV

class SignerVerificationMiddleware:
    """
    Middleware that verifies the signature for each request to the multisig API.
    Checks that the xpub, signature, and message headers are present.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if 'multisig' not in request.path:
            return self.get_response(request)
        LOGGER.info(request.path)
        LOGGER.info(request.method)
        if '/api/multisig/wallets' in request.path and request.method == 'POST':
            return self.get_response(request)

        xpub = request.headers.get("X-Xpub")
        derivation_path = request.headers.get("X-Derivation-Path")
        signature = request.headers.get("X-Signature")
        message = request.headers.get("X-Message")
        algo = request.headers.get("X-Signature-Algo", "ecdsa")

        if not xpub or not signature or not message:
            return JsonResponse({"detail": "Missing auth headers"}, status=400)
        
        signer_id = request.GET.get("signer_id")

        if not signer_id:
            return JsonResponse({"detail": "Missing signer record id"}, status=403)
        
        try:
            signer = Signer.objects.get(id=signer_id)
        except Signer.DoesNotExist:
            return JsonResponse({"detail": "Signer not found in this wallet"}, status=403)

        # Extract nonce from the message (nonce:<nonce_value>`)
        nonce = message.split("nonce:")[-1]
        
        nonce_valid = nonce_cache.get(nonce) is not None
        if not nonce_valid:
            return JsonResponse({"detail": "Invalid message"}, status=403)

        address_index = get_address_index(signer.derivation_path)
        
        valid = verify_signature(message, signature, signer.xpub, address_index, algo)
        if not valid:
            return JsonResponse({"detail": "Signature verification failed"}, status=403)
        request.signer = signer  
        response = self.get_response(request)
        return response
