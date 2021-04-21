from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync

from django.conf import settings

from main.utils.events import EventHandler

import json
import logging


logger = logging.getLogger(__name__)


class Consumer(WebsocketConsumer):

    def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        logger.info(f"USER {self.user_id} CONNECTED!")
        self.room_name = f"{settings.WATCH_ROOM}_{self.user_id}"

        async_to_sync(self.channel_layer.group_add)(
            self.room_name,
            self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        logger.info(f"USER {self.user_id} DISCONNECTED!")
        async_to_sync(self.channel_layer.group_discard)(
            self.room_name,
            self.channel_name
        )

    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        logger.info(f'RECEIVED DATA from WEBSOCKET: {text_data_json}')
        
        address = text_data_json.get('address', None)
        if address is not None:
            events_handler = EventHandler()
            events_handler.watch(address)

    def send_update(self, data):
        def data['type']
        self.send(text_data=json.dumps(data))
