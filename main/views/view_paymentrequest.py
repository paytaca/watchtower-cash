import logging
import requests
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets, decorators
from rest_framework.response import Response

from main.serializers import (
    PaySerializer,
    PaymentDetailsSerializer,
)
from main.utils.paymentrequest import PaymentRequest

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

    @swagger_auto_schema(
        method="get",
        responses= {200: PaymentDetailsSerializer},
        manual_parameters=[
            openapi.Parameter(name="payment_url", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, required=True),
        ],
    )
    @decorators.action(methods=["get"], detail=False)    
    def fetch(self, request, *args, **kwargs):
        payment_url = request.query_params.get("payment_url")
        payment_request = PaymentRequest.get_payment_request(payment_url)
        if payment_request.error:
            return Response([payment_request.error],status=400)

        serializer = PaymentDetailsSerializer(payment_request)
        return Response(serializer.data)
