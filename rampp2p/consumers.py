from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from rampp2p.utils import unread_orders_count
from authentication.models import AuthToken
from rampp2p.models import Peer
from datetime import datetime
import json
import logging
logger = logging.getLogger(__name__)

class MarketPriceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.currency = self.scope['url_route']['kwargs']['currency']
        self.room_name = f'p2pxchange_market_price_{self.currency}'
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        await self.accept()
        data = { 
            'success': True,
            'type': 'ConnectionMessage',
            'extra': {
                'message': f"Subscribed to '{self.room_name}'" 
            }
        }
        await self.send(text_data=json.dumps(data))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_name,
            self.channel_name
        )

    async def send_message(self, event):
        data = event.get('message')
        await self.send(text_data=json.dumps(data))

class AdUpdatesConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.ad_id = self.scope['url_route']['kwargs']['ad_id']
        self.room_name = f'p2pxchange_ad_{self.ad_id}'
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        await self.accept()
        data = { 
            'success': True,
            'type': 'ConnectionMessage',
            'extra': {
                'message': f"Subscribed to '{self.room_name}'" 
            }
        }
        await self.send(text_data=json.dumps(data))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_name,
            self.channel_name
        )

    async def send_message(self, event):
        data = event.get('message')
        await self.send(text_data=json.dumps(data))

class OrderUpdatesConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.room_name = f'p2pxchange_order_{self.order_id}'
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        await self.accept()
        data = { 
            'success': True,
            'type': 'ConnectionMessage',
            'extra': {
                'message': f"Subscribed to '{self.room_name}'" 
            }
        }
        await self.send(text_data=json.dumps(data))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_name,
            self.channel_name
        )

    async def send_message(self, event):
        data = event.get('message')
        await self.send(text_data=json.dumps(data))

class GeneralUpdatesConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.wallet_hash = self.scope['url_route']['kwargs']['wallet_hash']
        self.room_name = f'p2pxchange_{self.wallet_hash[:8]}'
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        await self.accept()
        user = await self.get_user_from_wallet_hash(self.wallet_hash)
        await self.set_user_active(user, True)
        unread_count = await unread_orders_count(self.wallet_hash)
        data = { 
            'success': True,
            'type': 'ConnectionMessage',
            'extra': {
                'message': f"Subscribed to '{self.room_name}'", 
                'unread_count': unread_count
            }
        }
        await self.send(text_data=json.dumps(data))

    async def disconnect(self, close_code):
        user = await self.get_user_from_wallet_hash(self.wallet_hash)
        await self.set_user_active(user, False)
        await self.channel_layer.group_discard(
            self.room_name,
            self.channel_name
        )

    async def send_message(self, event):
        data = event.get('message')
        await self.send(text_data=json.dumps(data))

    @sync_to_async
    def get_user_from_wallet_hash(self, wallet_hash):
        try:
            user = Peer.objects.get(wallet_hash=wallet_hash)
            return user
        except AuthToken.DoesNotExist:
            return None
    
    @sync_to_async
    def set_user_active(self, user, is_active):
        if user:
            user.is_online = is_active
            user.last_online_at = datetime.now()
            user.save()

class CashinAlertsConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.wallet_hash = self.scope['url_route']['kwargs']['wallet_hash']
        self.room_name = f'p2pxchange_cashin_{self.wallet_hash[:8]}'
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        await self.accept()

        user = await self.get_user_from_wallet_hash(self.wallet_hash)
        await self.set_user_active(user, True)

        data = { 
            'success': True,
            'type': 'ConnectionMessage',
            'extra': {
                'message': f"Subscribed to '{self.room_name}'", 
            }
        }
        await self.send(text_data=json.dumps(data))

    async def disconnect(self, close_code):
        user = await self.get_user_from_wallet_hash(self.wallet_hash)
        await self.set_user_active(user, False)
        await self.set_user_active(user, False)
        await self.channel_layer.group_discard(
            self.room_name,
            self.channel_name
        )

    async def send_message(self, event):
        data = event.get('message')
        await self.send(text_data=json.dumps(data))

    @sync_to_async
    def get_user_from_wallet_hash(self, wallet_hash):
        try:
            user = Peer.objects.get(wallet_hash=wallet_hash)
            return user
        except AuthToken.DoesNotExist:
            return None

    @sync_to_async
    def set_user_active(self, user, is_active):
        if user:
            user.is_online = is_active
            user.last_online_at = datetime.now()
            user.save()