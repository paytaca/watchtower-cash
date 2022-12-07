import logging
from asgiref.sync import async_to_sync
from django.conf import settings
from django.utils import timezone
from .rpc_consumer import RPCWebSocketConsumer, RPCRequest

logger = logging.getLogger("main")
REDIS_CLIENT = settings.REDISKV

class PaytacaPosUpdatesConsumer(RPCWebSocketConsumer):
    async def connect(self):
        self.wallet_hash = self.scope['url_route']['kwargs']['wallet_hash']
        try:
            self.posid = int(self.scope['url_route']['kwargs'].get('posid', None))
        except (ValueError, TypeError):
            self.posid = None

        logger.info(f"CONNECTING WEBSOCKET: {self.room_name}")
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        await self.accept()
        logger.info(f"WEBSOCKET CONNECTED: {self.room_name}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_name,
            self.channel_name
        )
        logger.info(f"WEBSOCKET DISCONNECTED: {self.room_name}")

    @property
    def room_name(self):
        room_name = f"paytacapos-{self.wallet_hash}"
        if isinstance(self.posid, int):
            room_name = room_name + f"-{self.posid}"

        return room_name

    @property
    def ping_redis_key(self):
        return self.construct_ping_redis_key(wallet_hash=self.wallet_hash, posid=self.posid)

    @classmethod
    def construct_ping_redis_key(self, wallet_hash=None, posid=None):
        return f"paytacapos-ping:{wallet_hash}:{posid}"

    async def send_update(self, data):
        del data["type"]
        data = data["data"]
        data = { "update": data }
        await self.send(
            RPCRequest(jsonrpc="2.0").construct_response(data, encode=True)
        )

    async def rpc_ping(self, request, *args):
        if isinstance(self.posid, int):
            timestamp = timezone.now().timestamp()
            REDIS_CLIENT.set(self.ping_redis_key, timestamp, ex=60)
            await self.channel_layer.group_send(
                f"paytacapos-{self.wallet_hash}",
                {
                    "type": "send_update",
                    "data": {
                        "resource": "pos_device",
                        "action": "ping",
                        "object": {
                            "wallet_hash": self.wallet_hash,
                            "posid": self.posid,
                        },
                        "data": { "timestamp": timestamp },
                    }
                }
            )
        return "PONG"

    def rpc_last_active(self, request, wallet_hash, posid, *args):
        ping_redis_key = self.construct_ping_redis_key(wallet_hash=wallet_hash, posid=posid)
        last_active = REDIS_CLIENT.get(ping_redis_key)
        if last_active:
            return last_active.decode()
