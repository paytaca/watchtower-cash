from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from .serializers import PushRegisterSerializer, PushUnregisterSerializer
from .authentication import BitcoinCashOAuthAuthentication
from .models import NostrPubkeyDevice


class PushRegisterView(APIView):
    authentication_classes = [BitcoinCashOAuthAuthentication]
    permission_classes = []
    serializer_class = PushRegisterSerializer

    @swagger_auto_schema(
        request_body=PushRegisterSerializer,
        responses={201: PushRegisterSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "registered"}, status=status.HTTP_201_CREATED)


class PushUnregisterView(APIView):
    authentication_classes = [BitcoinCashOAuthAuthentication]
    permission_classes = []
    serializer_class = PushUnregisterSerializer

    @swagger_auto_schema(
        request_body=PushUnregisterSerializer,
        responses={200: PushUnregisterSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "unregistered"}, status=status.HTTP_200_OK)


class PushCheckView(APIView):
    """Check if a Nostr pubkey has registered push notifications."""
    permission_classes = []

    def get(self, request, pubkey_hex, *args, **kwargs):
        is_registered = NostrPubkeyDevice.objects.filter(pubkey_hex=pubkey_hex).exists()
        return Response({
            "pubkey_hex": pubkey_hex,
            "registered": is_registered,
        }, status=status.HTTP_200_OK)
