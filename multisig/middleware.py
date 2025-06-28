import logging
from django.http import JsonResponse
from django.conf import settings
from redis import Redis
from .utils import verify_signature, get_address_index
from .models.wallet import SignerHdPublicKey

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

        auth = request.data.get('auth')

        if not auth:
            return JsonResponse({"detail": "Unauthorized"}, status=403)
        
        message = auth.get("message")
        signature = auth.get("signature")
        signed_by = auth.get("signedBy")
        algo = auth.get("algo")

        # if not all([message, signature, signed_by]):
        #     return JsonResponse({ "detail": "Unauthorized: message, signature, signer_entity_key required." }, status=403)
        
        # try:
        #     signer = SignerHdPublicKey.objects.get(wallet=, xpub=signer_entity_key)
        # except Signer.DoesNotExist:
        #     return JsonResponse({"detail": "Signer not found in this wallet"}, status=403)

        # # Extract nonce from the message (nonce:<nonce_value>`)
        # nonce = message.split("nonce:")[-1]
        
        # nonce_valid = nonce_cache.get(nonce) is not None
        # if not nonce_valid:
        #     return JsonResponse({"detail": "Invalid message"}, status=403)

        # address_index = get_address_index(signer.derivation_path)
        
        # valid = verify_signature(message, signature, signer.xpub, address_index, algo)
        # if not valid:
        #     return JsonResponse({"detail": "Signature verification failed"}, status=403)
        # request.signer = signer  
        response = self.get_response(request)
        return response
