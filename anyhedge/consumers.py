import json
from asgiref.sync import async_to_sync
from channels.generic.websocket import AsyncJsonWebsocketConsumer

class AnyhedgeUpdatesConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.wallet_hash = self.scope["url_route"]["kwargs"]["wallet_hash"]
        self.room_name = f"updates_{self.wallet_hash}"
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_name,
            self.channel_name
        )

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        if text_data == "PING":
            await self.send("PONG")
 
    async def send_update(self, data):
        del data["type"]
        data = data["data"]
        await self.send(json.dumps(data))
