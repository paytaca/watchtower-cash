from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
import json
import asyncio

class RampP2PUpdatesConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.room_name = f'ramp-p2p-updates-{self.order_id}'
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        await self.accept()
        await self.send(text_data=f"You are in room '{self.room_name}'")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.channel_name,
            self.channel_name
        )

    async def notify(self, event):
        data = event['data']
        await self.send(text_data=json.dumps(data))
