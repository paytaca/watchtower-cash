from django.contrib.auth import authenticate
from rest_framework.views import APIView
from rest_framework.response import Response
# from main.models import Wallet
from rampp2p.models import Peer as Wallet

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
            return Response({'token': wallet.auth_token})
        else:
            # Authentication failed
            return Response({'error': 'Invalid signature'}, status=400)

class AuthNonceView(APIView):
    def get(self, request, wallet_hash):
        try:
            wallet = Wallet.objects.get(wallet_hash=wallet_hash)
            wallet.update_auth_nonce()
            return Response({'auth_nonce': wallet.auth_nonce})
        except Wallet.DoesNotExist:
            return Response({'error': 'Wallet not found'}, status=404)
