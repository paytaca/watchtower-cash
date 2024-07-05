from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from main.models import Wallet as MainWallet
from rampp2p.models import Peer as PeerWallet
from rampp2p.models import Arbiter as ArbiterWallet
from rampp2p.serializers import PeerProfileSerializer, ArbiterSerializer
from authentication.backends import SignatureBackend
from authentication.models import AuthToken

import authentication.serializers as serializers
import rampp2p.models as rampmodels

from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken

from authentication.token import TokenAuthentication, WalletAuthentication

import logging
logger = logging.getLogger(__name__)

class LoginView(APIView):
    def post(self, request):

        wallet_hash=request.data.get('wallet_hash')
        signature=request.data.get('signature')
        public_key=request.data.get('public_key')
        
        app='main'
        path = request.path
        if path == '/api/auth/login/main':
            app = 'main'
        if path == '/api/auth/login/peer':
            app = 'ramp-peer'
        if path == '/api/auth/login/arbiter':
            app = 'ramp-arbiter'

        backend = SignatureBackend()
        wallet, token, error = backend.authenticate(
            app=app,
            wallet_hash=wallet_hash,
            signature=signature,
            public_key=public_key
        )
        
        if wallet is not None and token is not None:
            # Check if user is disabled
            if not isinstance(wallet, MainWallet) and wallet.is_disabled:
                return Response({'error': 'Wallet is disabled'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Checking if token is valid:
            try:
                cipher_suite = Fernet(settings.FERNET_KEY)
                key = cipher_suite.decrypt(token.key).decode()
            except InvalidToken:
                return Response({'error': 'Token is invalid'}, status=status.HTTP_400_BAD_REQUEST)
            
            response = {
                'token': key,
                'expires_at': token.key_expires_at
            }

            serialized_wallet = None
            # if app == 'main':
            #     # serialized_wallet = WalletSerialized(wallet)
            if app == 'ramp-peer':
                serialized_wallet = PeerProfileSerializer(wallet)
                
            if app == 'ramp-arbiter':
                serialized_wallet = ArbiterSerializer(wallet)

            if serialized_wallet is not None:
                response['user'] = serialized_wallet.data

            return Response(response)
        else:
            # Authentication failed
            response = {
                'error': error if error is not None else 'Invalid signature'
            }
            return Response(response, status=400)

class AuthNonceView(APIView):
    def get(self, request):
        try:
            # TODO: cooldown
            wallet_hash = request.headers.get('wallet_hash')
            path = request.path
            wallet = None
            if path == '/api/auth/otp/main':
                wallet = MainWallet.objects.get(wallet_hash=wallet_hash)
            if path == '/api/auth/otp/peer':
                wallet = PeerWallet.objects.get(wallet_hash=wallet_hash)
            if path == '/api/auth/otp/arbiter':
                wallet = ArbiterWallet.objects.get(wallet_hash=wallet_hash)
            if wallet is None:
                return Response({'error': 'Wallet not found'}, status=404)
            
            auth_token, created = AuthToken.objects.get_or_create(wallet_hash=wallet_hash)
            auth_token.update_nonce()
            if created or auth_token.is_key_expired():
                auth_token.update_key()
            
            return Response({
                'otp': auth_token.nonce,
                'expires_at': auth_token.nonce_expires_at,
            })
        
        except (MainWallet.DoesNotExist, PeerWallet.DoesNotExist, ArbiterWallet.DoesNotExist):
            return Response({'error': 'Wallet not found'}, status=404)

class RevokeTokenView(APIView):
    authentication_classes = [TokenAuthentication]
    def post(self, request):
        try:
            wallet_hash = request.headers.get('wallet_hash')
            auth_token = AuthToken.objects.get(wallet_hash=wallet_hash)
            auth_token.delete()
        except AuthToken.DoesNotExist:
            return Response({'error': 'Token does not exist'}, status=400)
        
        return Response(status=200)
    
class UserView(APIView):
    @swagger_auto_schema(responses={200: serializers.UserSerializer})
    def get(self, request):
        wallet_hash = request.headers.get('wallet_hash')
        if wallet_hash is None:
            return Response({'error': 'wallet_hash is required'}, status=400)
        
        # get user
        user = rampmodels.Arbiter.objects.filter(wallet_hash=wallet_hash)
        if not user.exists():
            user = rampmodels.Peer.objects.filter(wallet_hash=wallet_hash)
        if not user.exists():
            return Response({'error': 'user does not exist'}, status=404)
        
        # get auth token
        auth_token = AuthToken.objects.filter(wallet_hash=wallet_hash)
        is_authenticated = False
        if auth_token.exists() and not auth_token.first().is_key_expired():
            is_authenticated = True
        
        user = user.first()
        user_info = {
            'id': user.id,
            'chat_identity_id': user.chat_identity_id,
            'public_key': user.public_key,
            'name': user.name,
            'address': user.address,
            'address_path': user.address_path,
            'is_arbiter': isinstance(user, rampmodels.Arbiter),
            'is_authenticated': is_authenticated
        }
        return Response(serializers.UserSerializer(user_info).data, status=200)


class WalletView(APIView):
    authentication_classes = [
        WalletAuthentication,
    ]

    @swagger_auto_schema(responses={200: serializers.WalletInfoSerializer})
    def get(self, request):
        if not isinstance(request.user, MainWallet):
            return Response({'error': 'authenticated identity is not a wallet'}, status=400)

        return Response(
            serializers.WalletInfoSerializer(request.user).data
        )
