from push_notifications.models import GCMDevice, APNSDevice
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from .serializers import (
    DeviceSubscriptionSerializer,
    DeviceUnsubscribeSerializer,
    DeviceWalletSerializer,
    SendPushNotificationSerializer,
)
from authentication.models import ApiTokenScopes
from authentication.authentication import ApiTokenAuthentication
from authentication.permissions import HasApiTokenScopePermission

    
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


class TestPushNotificationView(APIView):
    """Send a test push notification to a wallet hash"""

    def post(self, request, *args, **kwargs):
        from notifications.utils.send import send_push_notification_to_wallet_hashes

        wallet_hash = request.data.get('wallet_hash')
        if not wallet_hash:
            return Response({'error': 'wallet_hash is required'}, status=400)

        message = request.data.get('message', 'Test push notification')
        title = request.data.get('title', 'Test')

        try:
            gcm_response, apns_response = send_push_notification_to_wallet_hashes(
                [wallet_hash],
                message,
                title=title,
                extra={'type': 'test'},
            )

            return Response({
                'success': True,
                'wallet_hash': wallet_hash,
                'message': message,
                'title': title,
                'gcm_response': str(gcm_response) if gcm_response else None,
                'apns_response': str(apns_response) if apns_response else None,
            })
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
            }, status=500)


class SendPushNotificationView(APIView):
    serializer_class = SendPushNotificationSerializer

    authentication_classes = [
        ApiTokenAuthentication,
    ]

    permission_classes = [
        HasApiTokenScopePermission(
            name="PushNotifApiTokenScope",
            scopes=[ApiTokenScopes.PUSH_NOTIF],
            match_all=True,
        )
    ]

    @swagger_auto_schema(request_body=SendPushNotificationSerializer)
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(result)
