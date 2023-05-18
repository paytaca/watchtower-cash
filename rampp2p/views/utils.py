from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import Http404
from rampp2p import tasks
import logging
logger = logging.getLogger(__name__)

class VerifySignature(APIView):
    def post(self, request):
        pubkey_hex = request.data.get('pubkey_hex')
        signature_hex = request.data.get('signature_hex')
        message = request.data.get('message')

        if (signature_hex is None or message is None or pubkey_hex is None):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        
        logger.warning(f'message: "{message}", pubkey_hex: "{pubkey_hex}", signature_hex: "{signature_hex}"')
        result, error = self.verify_signature(pubkey_hex, signature_hex, message)
        return Response({'is_verified': result.get('is_verified')}, status=status.HTTP_200_OK)

    def verify_signature(self, public_key, signature, message):
        path = './rampp2p/escrow/src/'
        command = 'node {}signature.js {} {} {}'.format(
            path,
            public_key, 
            signature, 
            message
        )
        response = tasks.execute_subprocess(command)
        result = response.get('result')
        error = response.get('error')
        return result, error