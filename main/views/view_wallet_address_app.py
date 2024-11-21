
import requests
import base64
import redis
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import AllowAny
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from django.utils.crypto import get_random_string
# from django.core.cache import cache
from django.forms import model_to_dict
from django.conf import settings
from coincurve import PublicKey
from bitcash import format

from main.models import WalletAddressApp

class WalletAddressAppView(APIView):

    permission_classes = (AllowAny, )

    def post(self, request, *args, **kwargs):
        r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
        public_key_hex = request.data.get('public_key')
        signature_hex = request.data.get('signature')
        # message = pipe separated strings '<nonce>|<signer_address>|<app_name>|<app_url>'
        # example: abcdNonce|bchtest:qr244vwpanvv5hvy2gl9schhpe9a22ytq5m0kja3rv|CashTokens Studio|https://cashtokens.studio.cash

        message = request.data.get('message')
        nonce, signer_address, app_name, app_url, *discard = message.split('|')

        if not all([nonce, app_name, app_url, signer_address]):
            return Response({'success': False,  'error': 'Incomplete message object. nonce, app_name, app_url, signer_address required. '}, status=status.HTTP_400_BAD_REQUEST)
        if not r.get(nonce):
            return Response({'success': False,  'error': 'Unauthorized, invalid nonce'}, status=status.HTTP_401_UNAUTHORIZED)

        # If signature is base64
        # decoded_bytes = base64.b64decode(base64_string)
        # hex_string = decoded_bytes.hex()

        public_key_bytes = bytes.fromhex(public_key_hex)
        signature_bytes = bytes.fromhex(signature_hex)
        
        # Ref: https://github.com/pybitcash/bitcash/blob/master/bitcash/format.py#L117
        address_version = 'test' if (settings.BCH_NETWORK or '').lower() == 'chipnet' else 'main' 
        cash_address_from_public_key = format.public_key_to_address(public_key_bytes, address_version)
        cash_address_from_signed_message = signer_address

        if cash_address_from_public_key != cash_address_from_signed_message:
            return Response({'success': 
                False, 
                'error': 'Address and public key doesn\'t match', 
                'data': request.data 
            }, status=status.HTTP_400_BAD_REQUEST)

        coincurve_public_key = PublicKey(public_key_bytes)
        message_bytes = message.encode('utf-8')  # encode message first
        if coincurve_public_key.verify(signature_bytes, message_bytes):
            wallet_address_app, created = WalletAddressApp.objects.get_or_create(
                wallet_address=signer_address,
                app_name=app_name,
                app_url=app_url,
                defaults = { 
                    'app_name': app_name, 
                    'app_url': app_url, 
                    'wallet_address': signer_address 
                }
            )
            r.delete(nonce)
            return Response({
                'success': True, 
                'message': f'Signature verification ok, data processed successfully',
                'data': model_to_dict(wallet_address_app)
            })

        return Response({'success': False, 'error': 'Failed saving, post data', 'data': request.data }, status=status.HTTP_401_UNAUTHORIZED)

class WalletAddressAppRecordExistsView(APIView):

    permission_classes = (AllowAny, )

    @swagger_auto_schema(
        operation_description="Object indicating that address was connected to an (D)app",
        responses={status.HTTP_200_OK: openapi.Response(
            description="Object indicating that address was connected to an (D)app",
            examples={
                'application/json': { 'exists': True }
            },
            type=openapi.TYPE_OBJECT
        )}
    )
    def get(self, request, *args, **kwargs):
        wallet_address = request.query_params.get('wallet_address', '')
        app_name = request.query_params.get('app_name', '')
        queryset = WalletAddressConnectedApp.objects.filter(wallet_address=wallet_address)
        
        if app_name:
            queryset = queryset.filter(app_name=app_name)

        if not queryset.exists():
            return Response({ 'exists': False })

        return Response({ 'exists': True })
        
class NonceAPIView(APIView):

    permission_classes = (AllowAny, )

    def get(self, request):
        r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT)

        try_again = 100
        nonce = None
        while not nonce and try_again:
            nonce = get_random_string(10)
            if not r.get(nonce):
                break
            try_again -= 1

        if not nonce:
            return Response({'status':'error', 'message': 'Please try again.'})   
        r.setex(nonce, 60 * 10, 1) # a-nonce-as-key, 10 minutes expiry, a-nonce-value-irrelevant 
        return Response({'status': 'success', 'data': { 'nonce': nonce }})

