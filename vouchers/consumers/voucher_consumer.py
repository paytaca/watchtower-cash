from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync

from django.conf import settings

from vouchers.websocket import send_websocket_data

import logging
import json


logger = logging.getLogger(__name__)


class VoucherConsumer(WebsocketConsumer):

    def connect(self):
        self.merchant_address = self.scope['url_route']['kwargs']['merchant_address']
        parsed_merchant_addr = self.merchant_address.split(':')[1]
        self.room_name = f"{settings.VOUCHER_ROOM}_{parsed_merchant_addr}"
        
        logger.info(f"USER {self.merchant_address} CONNECTED!")
        async_to_sync(self.channel_layer.group_add)(
            self.room_name,
            self.channel_name
        )
        self.accept()


    def disconnect(self, close_code):
        logger.info(f"USER {self.merchant_address} DISCONNECTED!")
        async_to_sync(self.channel_layer.group_discard)(
            self.room_name,
            self.channel_name
        )


    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        data = text_data_json['data']
        logger.info(f'RECEIVED WS DATA: {data}')
        send_websocket_data(self.merchant_address, operation, data)


    def send_data(self, event):
        data = event['data']

        logger.info('SENDING DATA\n')
        logger.info(event)

        self.send(text_data=json.dumps(data))
