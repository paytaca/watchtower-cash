from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError
from rampp2p.utils.transaction import validate_transaction
from rampp2p.models import Peer, MarketRate, Transaction
from rampp2p.serializers import MarketRateSerializer
# from main.utils.subscription import new_subscription, remove_subscription

import ecdsa
import hashlib
from ecdsa.util import sigdecode_der

import logging
logger = logging.getLogger(__name__)

class TransactionDetail(APIView):
    def get(self, request):
        txid = request.data.get('txid')
        wallet_hash = request.data.get('wallet_hash')
        if txid is None:
            return Response({"error": "txid field is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        utils.validate_transaction(txid, wallet_hashes=[wallet_hash])
        return Response(status=status.HTTP_200_OK)

class VerifyMessageView(APIView):
    def post(self, request):
        pubkey = request.data.get('pubkey')
        message = request.data.get('message')
        signature_hex = request.data.get('signature')
        
        valid = False
        try:
            valid = self.verify_signature(pubkey, signature_hex, message)
        except (ValidationError, Exception):
            valid = False
        return Response({"valid": valid}, status=status.HTTP_200_OK)
    
    def verify_signature(self, public_key_hex, signature_hex, message):
        try:

            # Convert the signature and public key to bytes
            der_signature_bytes = bytearray.fromhex(signature_hex)
            public_key_bytes = bytearray.fromhex(public_key_hex)

            # Create an ECDSA public key object
            vk = ecdsa.VerifyingKey.from_string(public_key_bytes, curve=ecdsa.SECP256k1)
            logger.warn(f'public_key: {public_key_hex}')
            logger.warn(f'message: {message}')

            # Verify the signature
            is_valid = vk.verify(der_signature_bytes, message.encode('utf-8'), hashlib.sha256, sigdecode=sigdecode_der)

            return is_valid

        except Peer.DoesNotExist as err:
            raise ValidationError({"error": err.args[0]})
    
class SubscribeAddress(APIView):
    def post(self, request):
        address = request.data.get('address')
        if address is None:
            return Response({"error": "address field is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        # result = new_subscription(address=address)
        result = None
        return Response(result, status=status.HTTP_200_OK)
    
class MarketRates(APIView):
    def get(self, request):
        queryset = MarketRate.objects.all()
        currency = request.query_params.get('currency')
        if currency is not None:
            queryset = MarketRate.objects.filter(currency=currency)
        serializer = MarketRateSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

class ValidateTransaction(APIView):
    def post(self, request):
        txid = request.data.get('txid')
        if txid is None:
            return Response({'error': 'txid is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        action = request.data.get('action')
        if action is None:
            return Response({'error': 'action is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if (action != Transaction.ActionType.ESCROW and
            action != Transaction.ActionType.RELEASE and 
            action != Transaction.ActionType.REFUND):
            return Response({'error': 'invalid action'}, status=status.HTTP_400_BAD_REQUEST)
        
        contract_id = request.data.get('contract_id')
        if contract_id is None:
            return Response({'error': 'contract_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        response = validate_transaction(
            txid=txid,
            action=Transaction.ActionType.RELEASE,
            contract_id=contract_id
        )
        return Response(response, status=status.HTTP_200_OK)