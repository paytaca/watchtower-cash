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
