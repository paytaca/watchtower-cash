import logging
import requests
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets, decorators
from rest_framework.response import Response

from main.serializers import PaySerializer

LOGGER = logging.getLogger("main")
ca_path = requests.certs.where()

class PaymentRequestViewSet(viewsets.GenericViewSet):
    @swagger_auto_schema(method="post", request_body=PaySerializer)
    @decorators.action(methods=["post"], detail=False)
    def pay(self, request, *args, **kwargs):
        serializer = PaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.construct()
        success, message = serializer.send()
        data = { "success": success, "message": message }
        return Response(data, status = 200 if success else 400)
