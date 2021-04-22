from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync

from django.conf import settings

from main.utils.events import EventHandler
from main.models import Subscription
import json
import logging


logger = logging.getLogger(__name__)


class Consumer(WebsocketConsumer):

    def connect(self):
        self.address = self.scope['url_route']['kwargs']['address']
        logger.info(self.address)
        if self.address.startswith('simpleledger'):
            Subscription.objects.filter(slp__address='simpleledger:' + self.address).update(websocket=True)

        elif self.address.startswith('bitcoincash'):
            Subscription.objects.filter(bch__address='bitcoincash:' + self.address).update(websocket=True)
            
        self.room_name = self.address.replace(':', '_')
        logger.info(f"ADDRESS {self.room_name} CONNECTED!")
        async_to_sync(self.channel_layer.group_add)(
            self.room_name,
            self.channel_name
        )
        self.accept()


    def disconnect(self, close_code):
        logger.info(f"ADDRESS {self.address} DISCONNECTED!")
        async_to_sync(self.channel_layer.group_discard)(
            self.room_name,
            self.channel_name
        )
        
    def send_update(self, data):
        logging.info(f'FOUND {data}')
        del data["type"]
        data = data['data']
        self.send(text_data=json.dumps(data))
