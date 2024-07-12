from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


class QrScanNotificationView(APIView):

    def post(self, request, *args, **kwargs):
        address = kwargs.get('bchaddress', '')
        response = {}

        if address:
            data = { 'message': 'Someone has scanned the QR, payment initiated.' }
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
