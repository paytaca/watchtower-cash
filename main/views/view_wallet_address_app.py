from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from django.utils.crypto import get_random_string
from django.core.cache import cache
from main.models import 

class WalletAddressWasConnectedView(APIView):

    @swagger_auto_schema(
        operation_description="Returns True if an address was connected to an App or Dapp",
        responses={status.HTTP_200_OK: openapi.Response(
            description="Object indicating that address was connected to an App",
            examples={
                'application/json': { 'connected': True }
            },
            type=openapi.TYPE_OBJECT
        )}
    )
    def get(self, request, *args, **kwargs):
        wallet_address = kwargs.get('wallet_address', '')
        queryset = WalletAddressConnectedApp.objects.filter(wallet_address=wallet_address)
        if not queryset.exists():
            return Response({ 'connected': False })

        return Response({ 'connected': True })

        
class NonceAPIView(APIView):

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
        cache.set(nonce, time.time(), timeout=120)
        return Response({'status': 'success', 'data': { 'nonce': nonce }})