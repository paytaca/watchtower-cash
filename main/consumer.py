from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync

from django.conf import settings

from main.utils.events import EventHandler
from main.utils.redis_address_manager import BCHAddressManager
from main.models import Address, Subscription
import json
import logging


logger = logging.getLogger(__name__)


class Consumer(WebsocketConsumer):

    def connect(self):
        self.wallet_hash = self.scope['url_route']['kwargs'].get('wallet_hash')
        self.address = self.scope['url_route']['kwargs'].get('address')
        self.tokenid = self.scope['url_route']['kwargs'].get('tokenid') or ''

        if self.wallet_hash:
            self.room_name = self.wallet_hash
            logger.info(f"WS WATCH FOR WALLET {self.wallet_hash} CONNECTED!")
        
        if self.address:
            self.room_name = self.address.replace(':', '_')
            self.room_name += f'_{self.tokenid}'
            logger.info(f"WS WATCH FOR ADDRESS {self.room_name} CONNECTED!")

            # Track address in Redis for mempool listener
            count = BCHAddressManager.add_address(self.address)
            logger.info(f"Address {self.address} now has {count} active websocket connection(s)")
            
            # Update database subscription status
            Subscription.objects.filter(address__address=self.address).update(websocket=True)

        async_to_sync(self.channel_layer.group_add)(
            self.room_name,
            self.channel_name
        )

        self.accept()

    def disconnect(self, close_code):
        if self.wallet_hash:
            logger.info(f"WS WATCH FOR WALLET {self.room_name} DISCONNECTED!")
        if self.address:
            logger.info(f"WS WATCH FOR ADDRESS {self.room_name} DISCONNECTED!")
        
        async_to_sync(self.channel_layer.group_discard)(
            self.room_name,
            self.channel_name
        )

        if self.address:
            room_name = self.room_name.split('_')
            address = ':'.join(room_name[:2])
            
            # Remove address from Redis tracking
            count = BCHAddressManager.remove_address(address)
            logger.info(f"Address {address} now has {count} active websocket connection(s) remaining")
            
            # Update database subscription status only if no more connections
            if count == 0:
                addr = Address.objects.get(address=address)
                Subscription.objects.filter(address=addr).update(websocket=False)
        
    def send_update(self, data):
        logging.info(f'FOUND {data}')
        del data["type"]
        data = data['data']
        self.send(text_data=json.dumps(data))
