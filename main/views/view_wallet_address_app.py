
import requests
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import AllowAny
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from django.utils.crypto import get_random_string
from django.core.cache import cache
from django.forms import model_to_dict
from main.models import 

main_jsserver_base_url='http://localhost:3000'

def verify_signature(bch_address, message, signature):
        return requests.post(f'{main_jsserver_base_url}/verify-signature', json={'bch_address': bch_address, 'message': message, 'signature': signature})

class WalletAddressAppView(APIView):

    permission_classes = (AllowAny, )

    def post(self, request, *args, **kwargs):

        signer_address = request.data.get('signer_address')
        signature = request.data.get('signature')
        message = request.data.get('message')
        parsed_message = json.loads(message)
        nonce = parsed_message['nonce']
        app_name = parsed_message['app_name']
        app_url  = parsed_message['app_url']
        wallet_address = parsed_message['signer_address']

        if not cache.get(nonce):
            return Response({'status': 'error', 'message': 'Unauthorized, invalid nonce'}, status=status.HTTP_401_UNAUTHORIZED)
        
        signature_verification_result = verify_signature(
            signer_address,
            message,
            signature
        )
        if signature_verification_result.ok:
            signature_verification_result = signature_verification_result.json()
            logger.info(signature_verification_result)
            if signature_verification_result['details']['signatureValid']:
                wallet_address_app, created = WalletAddressAppView.get_or_create(
                    wallet_address=wallet_address,
                    app_name=app_name,
                    app_url=app_url,
                    defaults = { 
                        'app_name': app_name, 
                        'app_url': app_url, 
                        'wallet_address': wallet_address 
                    }
                )
                
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
        try_again = 100
        nonce = None
        while not nonce and try_again:
            nonce = get_random_string(6)
            if not cache.get(nonce):
                break
            try_again -= 1

        if not nonce:
            return Response({'status':'error', 'message': 'Please try again.'})   
        cache.set(nonce, time.time(), timeout=300)
        return Response({'status': 'success', 'data': { 'nonce': nonce }})