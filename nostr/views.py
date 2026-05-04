from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from .serializers import PubkeyRegisterSerializer, PubkeyUnregisterSerializer
from .authentication import BitcoinCashOAuthAuthentication
from .models import NostrPubkey


class PubkeyRegisterView(APIView):
    authentication_classes = [BitcoinCashOAuthAuthentication]
    permission_classes = []
    serializer_class = PubkeyRegisterSerializer

    @swagger_auto_schema(
        request_body=PubkeyRegisterSerializer,
        responses={201: PubkeyRegisterSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "registered"}, status=status.HTTP_201_CREATED)


class PubkeyUnregisterView(APIView):
    authentication_classes = [BitcoinCashOAuthAuthentication]
    permission_classes = []
    serializer_class = PubkeyUnregisterSerializer

    @swagger_auto_schema(
        request_body=PubkeyUnregisterSerializer,
        responses={200: PubkeyUnregisterSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "unregistered"}, status=status.HTTP_200_OK)


class PubkeyCheckView(APIView):
    """Check if a Nostr pubkey is registered with watchtower."""
    permission_classes = []

    def get(self, request, pubkey_hex, *args, **kwargs):
        is_registered = NostrPubkey.objects.filter(pubkey_hex=pubkey_hex).exists()
        return Response({
            "pubkey_hex": pubkey_hex,
            "registered": is_registered,
        }, status=status.HTTP_200_OK)
