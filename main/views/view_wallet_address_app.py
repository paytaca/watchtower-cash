
import time
import requests
import base64
import redis
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework import pagination, response
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from django.utils.crypto import get_random_string
from collections import OrderedDict
from django.forms import model_to_dict
from django.conf import settings
from coincurve import PublicKey
from bitcash import format

from main.models import WalletAddressApp, Address
from main.pagination import CustomLimitOffsetPagination
from main.serializers import WalletAddressAppSerializer

nonce_cache = settings.REDISKV

class WalletAddressAppView(APIView):

    permission_classes = (AllowAny, )
    pagination_class = CustomLimitOffsetPagination
    serializer_class = WalletAddressAppSerializer

    def get(self, request, *args, **kwargs):
        wallet_hash = self.request.query_params.get('wallet_hash')
        wallet_address = self.request.query_params.get('wallet_address')
        app_name = request.query_params.get('app_name', '')
        app_url = request.query_params.get('app_url', '')
        
        queryset = WalletAddressApp.objects.order_by('-updated_at')

        if wallet_hash:
            queryset = queryset.filter(wallet_hash=wallet_hash)
        if wallet_address:
            queryset = queryset.filter(wallet_address=wallet_address)
        if app_name:
            queryset = queryset.filter(app_name=app_name)
        if app_url:
            queryset = queryset.filter(app_url=app_url)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data)
        
    def post(self, request, *args, **kwargs):
        
        public_key_hex = request.data.get('public_key')
        signature_hex = request.data.get('signature')
        app_icon = request.data.get('extra', {}).get('app_icon', '')
        # message = pipe separated strings '<nonce get from api/nonce endpoint (NonceAPIView) >|<signer_address>|<app_name>|<app_url>'
        # example: abcdNonce|bchtest:qr244vwpanvv5hvy2gl9schhpe9a22ytq5m0kja3rv|CashTokens Studio|https://cashtokens.studio.cash
        message = request.data.get('message')
        nonce, signer_address, app_name, app_url, *discard = message.split('|')

        if not all([nonce, app_name, app_url, signer_address]):
            return Response({'success': False,  'error': 'Incomplete message object. nonce, app_name, app_url, signer_address required. '}, status=status.HTTP_400_BAD_REQUEST)
        if not nonce_cache.get(nonce):
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
            address = Address.objects.filter(address=signer_address).first()
            wallet_hash = None
            if address and address.wallet:
                wallet_hash = address.wallet.wallet_hash
            wallet_address_app, created = WalletAddressApp.objects.update_or_create(
                wallet_address=signer_address,
                app_name=app_name,
                app_url=app_url,
                defaults = { 
                    'app_name': app_name, 
                    'app_url': app_url, 
                    'app_icon': app_icon,
                    'wallet_address': signer_address,
                    'wallet_hash': wallet_hash,

                }
            )
            nonce_cache.delete(nonce)
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
        operation_id="wallet_address_app_record_exists",
        responses={status.HTTP_200_OK: openapi.Response(
            description="Object indicating that address was connected to an (D)app",
            examples={
                'application/json': { 'exists': True }
            },
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'exists': openapi.Schema(type=openapi.TYPE_BOOLEAN)
                }
            )
        )}
    )
    def get(self, request, *args, **kwargs):
        wallet_address = request.query_params.get('wallet_address', '')
        wallet_hash = request.query_params.get('wallet_hash', '')
        app_name = request.query_params.get('app_name', '')
        app_url = request.query_params.get('app_url', '')
        queryset = WalletAddressApp.objects.all()
        if wallet_hash:
            queryset = queryset.filter(wallet_hash=wallet_hash)
        if wallet_address:
            queryset = queryset.filter(wallet_address=wallet_address)
        if app_name:
            queryset = queryset.filter(app_name=app_name)
        if app_url:
            queryset = queryset.filter(app_url=app_url)
        return Response({ 'exists': queryset.exists() })

        
class NonceAPIView(APIView):

    permission_classes = (AllowAny, )

    def get(self, request):
        time.sleep(1)
        try_again = 100
        nonce = None
        while not nonce and try_again:
            nonce = get_random_string(10)
            if not nonce_cache.get(nonce):
                break
            try_again -= 1

        if not nonce:
            return Response({'success': False, 'error': 'Unable to generate nonce. Please try again later!'})   
        nonce_cache.setex(nonce, 60 * 3, 1) # a-nonce-as-key, 3 minutes expiry, a-nonce-value-irrelevant 
        return Response({'success': True, 'data': { 'nonce': nonce }})

