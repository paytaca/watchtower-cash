from push_notifications.models import GCMDevice, APNSDevice
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from .serializers import (
    DeviceSubscriptionSerializer,
    DeviceUnsubscribeSerializer,
    DeviceWalletSerializer,
)

    
# Create your views here.
class DeviceSubscriptionView(APIView):
    serializer_class = DeviceSubscriptionSerializer

    @swagger_auto_schema(request_body=DeviceSubscriptionSerializer, responses={201: DeviceSubscriptionSerializer})
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=201)


class DeviceUnsubscribeView(APIView):
    serializer_class = DeviceUnsubscribeSerializer

    @swagger_auto_schema(request_body=DeviceUnsubscribeSerializer, responses={200: DeviceWalletSerializer(many=True)})
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        response_serializer = DeviceWalletSerializer(result, many=True)
        return Response(response_serializer.data, status=200)


class DeviceStatusView(APIView):
    """Get registered push notification devices for a wallet hash"""

    def get(self, request, *args, **kwargs):
        wallet_hash = request.query_params.get('wallet_hash')
        if not wallet_hash:
            return Response({'error': 'wallet_hash parameter required'}, status=400)

        gcm_devices = GCMDevice.objects.filter(
            device_wallets__wallet_hash=wallet_hash,
            active=True
        ).values('registration_id', 'device_id', 'cloud_message_type')

        apns_devices = APNSDevice.objects.filter(
            device_wallets__wallet_hash=wallet_hash,
            active=True
        ).values('registration_id', 'device_id')

        return Response({
            'wallet_hash': wallet_hash,
            'gcm_devices': list(gcm_devices),
            'apns_devices': list(apns_devices),
        })
