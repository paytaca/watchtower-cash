from channels.generic.websocket import AsyncWebsocketConsumer
from rampp2p.utils import unread_orders_count, update_user_active_status
from asgiref.sync import sync_to_async
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
        is_online = True
        await sync_to_async(update_user_active_status)(self.wallet_hash, is_online)
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
        is_online = False
        await sync_to_async(update_user_active_status)(self.wallet_hash, is_online)
        await self.channel_layer.group_discard(
            self.room_name,
            self.channel_name
        )

    async def send_message(self, event):
        data = event.get('message')
        await self.send(text_data=json.dumps(data))

class CashinAlertsConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.wallet_hash = self.scope['url_route']['kwargs']['wallet_hash']
        self.room_name = f'p2pxchange_cashin_{self.wallet_hash[:8]}'
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        await self.accept()

        is_online = True
        await sync_to_async(update_user_active_status)(self.wallet_hash, is_online)
        data = { 
            'success': True,
            'type': 'ConnectionMessage',
            'extra': {
                'message': f"Subscribed to '{self.room_name}'", 
            }
        }
        await self.send(text_data=json.dumps(data))

    async def disconnect(self, close_code):
        is_online = False
        await sync_to_async(update_user_active_status)(self.wallet_hash, is_online)
        await self.channel_layer.group_discard(
            self.room_name,
            self.channel_name
        )

    async def send_message(self, event):
        data = event.get('message')
        await self.send(text_data=json.dumps(data))