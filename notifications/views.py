from push_notifications.models import GCMDevice, APNSDevice
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from .serializers import DeviceSubscriptionSerializer

    
# Create your views here.
class DeviceSubscriptionView(APIView):
    serializer_class = DeviceSubscriptionSerializer

    @swagger_auto_schema(request_body=DeviceSubscriptionSerializer, responses={201: DeviceSubscriptionSerializer})
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=201)
