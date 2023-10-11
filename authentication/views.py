from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from main.models import Wallet as MainWallet
from rampp2p.models import Peer as PeerWallet
from rampp2p.models import Arbiter as ArbiterWallet
from rampp2p.serializers import PeerSerializer, ArbiterReadSerializer

from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken

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
            app = 'arbiter-peer'
        
        logger.warn(f'path: {path}')
        logger.warn(f'app: {app}')

        wallet = authenticate(
            app=app,
            wallet_hash=wallet_hash,
            signature=signature,
            public_key=public_key
        )
        
        if wallet is not None:
            # User is authenticated
            # Checking if token is valid:
            cipher_suite = Fernet(settings.FERNET_KEY)
            try:
                auth_token = cipher_suite.decrypt(wallet.auth_token).decode()
            except InvalidToken:
                return Response({'error': 'token is invalid'}, status=status.HTTP_400_BAD_REQUEST)
            
            response = {
                'token': auth_token,
            }

            serialized_wallet = None
            if app == 'ramp-peer':
                serialized_wallet = PeerSerializer(wallet)
            if app == 'arbiter-peer':
                serialized_wallet = ArbiterReadSerializer(wallet)

            if serialized_wallet is not None:
                response['user'] = serialized_wallet.data

            return Response(response)
        else:
            # Authentication failed
            return Response({'error': 'Invalid signature'}, status=400)

class RampPeerLoginView(APIView):
    def post(self, request):

        wallet_hash=request.data.get('wallet_hash')
        signature=request.data.get('signature')
        public_key=request.data.get('public_key')

        wallet = authenticate(
            app='ramp-peer',
            wallet_hash=wallet_hash,
            signature=signature,
            public_key=public_key
        )
        
        if wallet is not None:
            # User is authenticated
            # Checking if token is valid:
            cipher_suite = Fernet(settings.FERNET_KEY)
            try:
                auth_token = cipher_suite.decrypt(wallet.auth_token).decode()
            except InvalidToken:
                return Response({'error': 'token is invalid'}, status=status.HTTP_400_BAD_REQUEST)
            
            serialized_wallet = PeerSerializer(wallet)
            response = {
                'token': auth_token,
                'user': serialized_wallet.data
            }
            return Response(response)
        else:
            # Authentication failed
            return Response({'error': 'Invalid signature'}, status=400)

class RampArbiterLoginView(APIView):
    def post(self, request):

        wallet_hash=request.data.get('wallet_hash')
        signature=request.data.get('signature')
        public_key=request.data.get('public_key')

        wallet = authenticate(
            app='ramp-arbiter',
            wallet_hash=wallet_hash,
            signature=signature,
            public_key=public_key
        )
        
        if wallet is not None:
            # User is authenticated
            # Checking if token is valid:
            cipher_suite = Fernet(settings.FERNET_KEY)
            try:
                auth_token = cipher_suite.decrypt(wallet.auth_token).decode()
            except InvalidToken:
                return Response({'error': 'token is invalid'}, status=status.HTTP_400_BAD_REQUEST)
            
            serialized_wallet = ArbiterReadSerializer(wallet)
            response = {
                'token': auth_token,
                'user': serialized_wallet.data
            }
            return Response(response)
        else:
            # Authentication failed
            return Response({'error': 'Invalid signature'}, status=400)

class AuthNonceView(APIView):
    def get(self, request):
        try:
            # TODO: cooldown
            wallet_hash = request.headers.get('wallet_hash')

            path = request.path
            logger.warn(f'path: {path}')
            wallet = None
            if path == '/api/auth/otp/main':
                wallet = MainWallet.objects.get(wallet_hash=wallet_hash)
            if path == '/api/auth/otp/peer':
                wallet = PeerWallet.objects.get(wallet_hash=wallet_hash)
            if path == '/api/auth/otp/arbiter':
                wallet = ArbiterWallet.objects.get(wallet_hash=wallet_hash)
            if wallet is None:
                return Response({'error': 'Wallet for path not found'}, status=404)
            
            wallet.update_auth_nonce()
            wallet.create_auth_token()
            return Response({'otp': wallet.auth_nonce})
        except (MainWallet.DoesNotExist, PeerWallet.DoesNotExist, ArbiterWallet.DoesNotExist):
            return Response({'error': 'Wallet not found'}, status=404)
