from channels.generic.websocket import AsyncWebsocketConsumer
from rampp2p.utils import unread_orders_count, update_user_active_status
import json

import logging
logger = logging.getLogger(__name__)

class MarketRateConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.currency = self.scope['url_route']['kwargs']['currency']
        self.room_name = f'ramp-p2p-subscribe-market-price-{self.currency}'
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        await self.accept()
        data = { 'message': f"Subscribed to '{self.room_name}'" }
        await self.send(text_data=json.dumps(data))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.channel_name,
            self.channel_name
        )

    async def send_message(self, event):
        data = event.get('message')
        await self.send(text_data=json.dumps(data))


class OrderUpdatesConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.room_name = f'ramp-p2p-subscribe-order-{self.order_id}'
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        await self.accept()
        data = { 'message': f"Subscribed to '{self.room_name}'" }
        await self.send(text_data=json.dumps(data))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.channel_name,
            self.channel_name
        )

    async def send_message(self, event):
        data = event.get('message')
        await self.send(text_data=json.dumps(data))

class GeneralUpdatesConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.wallet_hash = self.scope['url_route']['kwargs']['wallet_hash']
        self.room_name = f'ramp-p2p-subscribe-general-{self.wallet_hash}'
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        await self.accept()
        is_online = True
        await update_user_active_status(self.wallet_hash, is_online)
        unread_count = await unread_orders_count(self.wallet_hash)
        data = { 
            'type': 'ConnectionMessage',
            'extra': {
                'message': f"Subscribed to '{self.room_name}'", 
                'unread_count': unread_count
            }
        }
        await self.send(text_data=json.dumps(data))

    async def disconnect(self, close_code):
        is_online = False
        await update_user_active_status(self.wallet_hash, is_online)

        await self.channel_layer.group_discard(
            self.channel_name,
            self.channel_name
        )

    async def send_message(self, event):
        data = event.get('message')
        await self.send(text_data=json.dumps(data))