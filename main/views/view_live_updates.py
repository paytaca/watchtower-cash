from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action

from drf_yasg.utils import swagger_auto_schema
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from main.serializers import (
    LiveUpdatesPaymentSerializer,
    LiveUpdatesPaymentResponseSerializer,
)


class LiveUpdatesPaymentView(APIView):

    @action(methods=['POST'], detail=False)
    @swagger_auto_schema(request_body=LiveUpdatesPaymentSerializer, responses={ 200: LiveUpdatesPaymentResponseSerializer })
    def post(self, request, *args, **kwargs):
        serializer = LiveUpdatesPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        address = serializer.validated_data['address']
        response = {}

        if address:
            data = { 'update_type': 'qr_scanned' }
            room_name = address.replace(':', '_')
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"{room_name}_", 
                {
                    "type": "send_update",
                    "data": data
                }
            )
            data['address'] = address
            response = data

        return Response(response, status=status.HTTP_200_OK)
