from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import Http404
from django.core.exceptions import ValidationError

from rampp2p.utils.signature import verify_signature
from rampp2p import utils
from rampp2p.tasks import contract_tasks
from rampp2p.models import Peer

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

class HashContract(APIView):
    def get(self, request):
        sha256_hash = hash.calculate_sha256("./rampp2p/escrow/src/escrow.cash")
        return Response({'sha256_hash': sha256_hash}, status=status.HTTP_200_OK)

class VerifySignature(APIView):
    def post(self, request):
        wallet_hash = request.data.get('wallet_hash')
        signature = request.data.get('signature')
        message = request.data.get('message')

        if (signature is None or message is None or wallet_hash is None):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        
        public_key = Peer.objects.values('public_key').get(wallet_hash=wallet_hash)['public_key']
        logger.warning(f'message: "{message}", pubkey_hex: "{public_key}", signature_hex: "{signature}"')

        try: 
            result, error = self.verify_signature(public_key, signature, message)
            # is_valid = verify_signature(public_key, signature, message)
            # logger.warn(f'result: {result}')
            # return Response({'is_verified': is_valid}, status=status.HTTP_200_OK)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'is_verified': result.get('is_verified')}, status=status.HTTP_200_OK)

    def verify_signature(self, public_key, signature, message):
        try:
            path = './rampp2p/escrow/src/'
            command = 'node {}signature.js verify {} {} {}'.format(
                path,
                public_key, 
                signature, 
                message
            )
            response = contract_tasks.execute_subprocess(command)
            result = response.get('result')
            error = response.get('error')
            return result, error
        except Exception as err:
            raise ValidationError(err.args[0])