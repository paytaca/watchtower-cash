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
        sig_hex = request.data.get('sig_hex')
        message = request.data.get('message')

        if (sig_hex is None or message is None or pubkey_hex is None):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        
        logger.warning(f'message: "{message}", pubkey_hex: "{pubkey_hex}", sig_hex: "{sig_hex}"')
        sig_valid = self.verify_signature(pubkey_hex, sig_hex, message)
        return Response({'sig_valid': sig_valid}, status=status.HTTP_200_OK)

    def verify_signature(self, public_key, signature, message):
        path = './rampp2p/escrow/src/'
        command = 'node {}signature.js {} {} {}'.format(
            path,
            public_key, 
            signature, 
            message
        )
        return tasks.execute_subprocess(command)