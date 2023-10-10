from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
# from main.models import Wallet
from rampp2p.models import Peer as Wallet
from rampp2p.serializers import PeerSerializer

from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken

import logging
logger = logging.getLogger(__name__)

class LoginView(APIView):
    def post(self, request):
        wallet_hash = request.data.get('wallet_hash')
        signature = request.data.get('signature')
        public_key = request.data.get('public_key')
        wallet = authenticate(request, wallet_hash=wallet_hash, signature=signature, public_key=public_key)
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

class AuthNonceView(APIView):
    def get(self, request):
        try:
            # TODO: cooldown
            wallet_hash = request.headers.get('wallet_hash')
            wallet = Wallet.objects.get(wallet_hash=wallet_hash)
            wallet.update_auth_nonce()
            wallet.create_auth_token()
            return Response({'otp': wallet.auth_nonce})
        except Wallet.DoesNotExist:
            return Response({'error': 'Wallet not found'}, status=404)
