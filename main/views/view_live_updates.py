from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from drf_yasg.utils import swagger_auto_schema
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from main.serializers import LiveUpdatesPaymentSerializer


class LiveUpdatesPaymentView(APIView):

    @swagger_auto_schema(request_body=LiveUpdatesPaymentSerializer, responses={ 200: LiveUpdatesPaymentSerializer })
    def post(self, request, *args, **kwargs):
        serializer = LiveUpdatesPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        address = serializer.data['address']
        room_name = address.replace(':', '_')
        
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"{room_name}_", 
            {
                "type": "send_update",
                "data": serializer.data
            }
        )

        return Response(serializer.data, status=status.HTTP_200_OK)
