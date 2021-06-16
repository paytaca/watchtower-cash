from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync

from django.conf import settings

from main.utils.events import EventHandler
from main.models import Address, Subscription
import json
import logging


logger = logging.getLogger(__name__)


class Consumer(WebsocketConsumer):

    def connect(self):
        self.address = self.scope['url_route']['kwargs']['address']
        self.tokenid = ''
        if 'tokenid' in self.scope['url_route']['kwargs'].keys():
            self.tokenid = self.scope['url_route']['kwargs']['tokenid']

        logger.info(self.address)
        Subscription.objects.filter(address__address=self.address).update(websocket=True)

        self.room_name = self.address.replace(':', '_')
        self.room_name += f'_{self.tokenid}'

        logger.info(f"ADDRESS {self.room_name} CONNECTED!")
        async_to_sync(self.channel_layer.group_add)(
            self.room_name,
            self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        logger.info(f"ADDRESS {self.room_name} DISCONNECTED!")
        async_to_sync(self.channel_layer.group_discard)(
            self.room_name,
            self.channel_name
        )
        room_name = self.room_name.split('_')
        address = ':'.join(room_name[:2])
        addr = Address.objects.get(address=address)
        Subscription.objects.filter(address=addr).update(websocket=False)
        
    def send_update(self, data):
        logging.info(f'FOUND {data}')
        del data["type"]
        data = data['data']
        self.send(text_data=json.dumps(data))
