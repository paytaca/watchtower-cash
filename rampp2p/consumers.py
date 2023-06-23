from channels.generic.websocket import AsyncWebsocketConsumer
import json

import logging
logger = logging.getLogger(__name__)

class MarketPriceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = f'ramp-p2p-market-price'
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        await self.accept()
        await self.send(text_data=f"Subscribed to '{self.room_name}'")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.channel_name,
            self.channel_name
        )

    async def send_message(self, event):
        data = event['data']
        logger.warning(f'send_message data: {data}')
        await self.send(text_data=json.dumps(data))


class OrderUpdatesConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.room_name = f'ramp-p2p-updates-{self.order_id}'
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        await self.accept()
        await self.send(text_data=f"Subscribed to '{self.room_name}'")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.channel_name,
            self.channel_name
        )

    async def send_message(self, event):
        data = event['data']
        await self.send(text_data=json.dumps(data))
