from channels.generic.websocket import JsonWebsocketConsumer
from asgiref.sync import async_to_sync
from django.utils import timezone
import json
import logging


logger = logging.getLogger(__name__)


class NostrUpdatesConsumer(JsonWebsocketConsumer):
    """General-purpose WebSocket for nostr-related real-time events.

    Requires Bearer-token authentication (via ``Authorization`` header or
    ``?token=`` query param) set up by ``BearerTokenAuthMiddleware``.

    When a message is received from a sender, each recipient gets a
    ``last_active`` event pushed to their WebSocket.

    SECURITY: This consumer only accepts ``{"type": "heartbeat"}``
    messages. All other inbound payloads are rejected.
    """

    def _update_last_active(self):
        """Record the wallet as active in DB and cache."""
        from .models import NostrPubkey
        from main.utils.cache import set_last_active

        logger.info(
            f'_update_last_active: looking up wallet_hash='
            f'{self.wallet_hash[:16]}...'
        )

        np = NostrPubkey.objects.filter(
            wallet_hash=self.wallet_hash,
        ).values('pubkey_hex').first()

        if np:
            now = timezone.now()
            NostrPubkey.objects.filter(wallet_hash=self.wallet_hash).update(
                last_active=now,
            )
            set_last_active(np['pubkey_hex'], now)
            logger.info(
                f'_update_last_active: updated for pubkey '
                f'{np["pubkey_hex"][:16]}..., ts={now.isoformat()}'
            )
        else:
            logger.warning(
                f'_update_last_active: no NostrPubkey found for wallet_hash '
                f'{self.wallet_hash[:16]}... — nothing updated'
            )

    def connect(self):
        self.wallet_hash = self.scope['url_route']['kwargs']['wallet_hash']

        # Enforce authentication — BearerTokenAuthMiddleware must have set user
        user = self.scope.get('user')
        if user is None or getattr(user, 'is_anonymous', True):
            logger.warning(
                f'Nostr WS rejected unauthenticated connection for wallet '
                f'{self.wallet_hash[:16]}...'
            )
            self.close(code=4001)
            return

        from .utils.auth import verify_wallet_ownership
        ok, reason = verify_wallet_ownership(user, self.wallet_hash)
        if not ok:
            logger.warning(
                f'Nostr WS rejected connection for wallet '
                f'{self.wallet_hash[:16]}... — {reason}'
            )
            self.close(code=4001)
            return

        self.room_group_name = f'nostr_updates_{self.wallet_hash}'

        logger.info(
            f'Nostr WS connected for wallet {self.wallet_hash[:16]}... '
            f'(user {getattr(user, "user_id", "?")})'
        )

        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name,
        )

        self.accept()
        self._update_last_active()

    def disconnect(self, close_code):
        # room_group_name may not exist if connect() rejected the connection early
        if not hasattr(self, 'room_group_name'):
            return

        logger.info(f'Nostr WS disconnected for wallet {self.wallet_hash[:16]}...')

        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name,
            self.channel_name,
        )

    def receive_json(self, content):
        if content != {"type": "heartbeat"}:
            logger.warning(
                f'Nostr WS rejected non-heartbeat from '
                f'{self.wallet_hash[:16]}...: {content}'
            )
            self.close(code=4001)
            return

        user = self.scope.get('user')
        from .utils.auth import verify_wallet_ownership
        ok, reason = verify_wallet_ownership(user, self.wallet_hash)
        if not ok:
            logger.warning(
                f'Nostr WS closing heartbeat for wallet '
                f'{self.wallet_hash[:16]}... — {reason}'
            )
            self.close(code=4001)
            return

        self._update_last_active()

    def last_active_update(self, event):
        """Send a last-active timestamp update to the client."""
        logger.info(
            f'Nostr WS received last_active_update for wallet '
            f'{self.wallet_hash[:16]}...: pubkey={event.get("pubkey_hex", "")[:16]}... '
            f'ts={event.get("timestamp")}'
        )
        self.send(text_data=json.dumps({
            'type': 'last_active',
            'pubkey_hex': event['pubkey_hex'],
            'timestamp': event['timestamp'],
        }))
