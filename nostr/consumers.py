from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync
import json
import logging


logger = logging.getLogger(__name__)


class NostrUpdatesConsumer(WebsocketConsumer):
    """General-purpose WebSocket for nostr-related real-time events.

    When a message is received from a sender, each recipient gets a
    ``last_active`` event pushed to their WebSocket with the **sender's**
    pubkey so their client can show the sender as active.

    The client connects as ``ws/nostr/updates/<wallet_hash>/``.

    SECURITY: This consumer is READ-ONLY. It does not implement receive()
    to prevent clients from sending fake updates that could be relayed.
    """

    def connect(self):
        self.wallet_hash = self.scope['url_route']['kwargs']['wallet_hash']
        self.room_group_name = f'nostr_updates_{self.wallet_hash}'

        logger.info(f'Nostr WS connected for wallet {self.wallet_hash[:16]}...')

        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name,
        )

        self.accept()

    def disconnect(self, close_code):
        logger.info(f'Nostr WS disconnected for wallet {self.wallet_hash[:16]}...')

        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name,
            self.channel_name,
        )

    def last_active_update(self, event):
        """Send a last-active timestamp update to the client.

        The ``pubkey_hex`` in the event is the sender (the person whose
        activity changed), not the owner of this WebSocket room.
        """
        self.send(text_data=json.dumps({
            'type': 'last_active',
            'pubkey_hex': event['pubkey_hex'],
            'timestamp': event['timestamp'],
        }))
