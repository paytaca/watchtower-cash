from channels.generic.websocket import AsyncWebsocketConsumer
from rampp2p.utils import unread_orders_count
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
        data = event.get('data')
        logger.warning(f'send_message data: {data}')
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
        data = event.get('data')
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
        await self.channel_layer.group_discard(
            self.channel_name,
            self.channel_name
        )

    async def send_message(self, event):
        data = event.get('data')
        await self.send(text_data=json.dumps(data))