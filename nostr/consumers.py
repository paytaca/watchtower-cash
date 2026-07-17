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

    Accepted inbound message types:
    - ``{"type": "heartbeat"}`` — refreshes the wallet's last-active.
    - ``{"type": "typing", "room_id": ..., "recipients": [...]}`` —
      broadcasts a typing indicator to each recipient.
    - ``{"type": "stop_typing", "room_id": ..., "recipients": [...]}`` —
      broadcasts a stop-typing signal to each recipient.

    All other inbound payloads are rejected with close code 4001.
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
        ).values('pubkey_hex', 'show_active_status').first()

        if np:
            if not np['show_active_status']:
                logger.info(
                    f'_update_last_active: skipping — show_active_status is '
                    f'False for wallet {self.wallet_hash[:16]}...'
                )
                return

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
        msg_type = content.get('type') if isinstance(content, dict) else None

        if msg_type == 'heartbeat':
            return self._handle_heartbeat()

        if msg_type == 'typing':
            return self._handle_typing(content)

        if msg_type == 'stop_typing':
            return self._handle_stop_typing(content)

        logger.warning(
            f'Nostr WS rejected unknown message type from '
            f'{self.wallet_hash[:16]}...: {content}'
        )
        self.close(code=4001)

    def _handle_heartbeat(self):
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

    def _handle_typing(self, content):
        import re
        from .models import NostrPubkey
        from .utils.auth import verify_wallet_ownership
        from main.utils.cache import set_typing_throttle
        from .utils.websocket import send_typing_update

        user = self.scope.get('user')
        ok, reason = verify_wallet_ownership(user, self.wallet_hash)
        if not ok:
            logger.warning(
                f'Nostr WS closing typing for wallet '
                f'{self.wallet_hash[:16]}... — {reason}'
            )
            self.close(code=4001)
            return

        room_id = content.get('room_id')
        recipients = content.get('recipients')

        if not room_id or not isinstance(room_id, str):
            logger.warning(
                f'Nostr WS rejected typing — missing/invalid room_id from '
                f'{self.wallet_hash[:16]}...'
            )
            self.close(code=4001)
            return

        if not recipients or not isinstance(recipients, list):
            logger.warning(
                f'Nostr WS rejected typing — missing/invalid recipients from '
                f'{self.wallet_hash[:16]}...'
            )
            self.close(code=4001)
            return

        MAX_RECIPIENTS = 500
        if len(recipients) > MAX_RECIPIENTS:
            logger.warning(
                f'Nostr WS rejected typing — too many recipients '
                f'({len(recipients)}) from {self.wallet_hash[:16]}...'
            )
            self.close(code=4001)
            return

        for pk in recipients:
            if not isinstance(pk, str) or not re.match(r'^[0-9a-fA-F]{64}$', pk):
                logger.warning(
                    f'Nostr WS rejected typing — invalid recipient pubkey '
                    f'from {self.wallet_hash[:16]}...'
                )
                self.close(code=4001)
                return

        normalized_recipients = [pk.lower() for pk in recipients]

        np = NostrPubkey.objects.filter(
            wallet_hash=self.wallet_hash,
        ).values('pubkey_hex', 'show_active_status').first()

        if not np:
            logger.warning(
                f'Nostr WS typing — no NostrPubkey for wallet '
                f'{self.wallet_hash[:16]}...'
            )
            return

        if not np['show_active_status']:
            logger.info(
                f'Nostr WS typing — skipping, sender show_active_status=False '
                f'for wallet {self.wallet_hash[:16]}...'
            )
            return

        sender_pubkey = np['pubkey_hex']

        if not set_typing_throttle(sender_pubkey, room_id):
            logger.info(
                f'Nostr WS typing — throttled for pubkey '
                f'{sender_pubkey[:16]}... room {room_id[:16]}...'
            )
            return

        room_map = {
            np_recip['pubkey_hex']: np_recip['wallet_hash']
            for np_recip in NostrPubkey.objects.filter(
                pubkey_hex__in=normalized_recipients,
            ).values('pubkey_hex', 'wallet_hash')
        }

        for recipient_pubkey in normalized_recipients:
            recipient_wallet = room_map.get(recipient_pubkey)
            if recipient_wallet:
                send_typing_update(recipient_wallet, sender_pubkey, room_id)
            else:
                logger.info(
                    f'Nostr WS typing — recipient {recipient_pubkey[:16]}... '
                    f'not found — skipping WS push'
                )

    def _handle_stop_typing(self, content):
        import re
        from django.conf import settings
        from .models import NostrPubkey
        from .utils.auth import verify_wallet_ownership
        from .utils.websocket import send_stop_typing_update

        user = self.scope.get('user')
        ok, reason = verify_wallet_ownership(user, self.wallet_hash)
        if not ok:
            logger.warning(
                f'Nostr WS closing stop_typing for wallet '
                f'{self.wallet_hash[:16]}... — {reason}'
            )
            self.close(code=4001)
            return

        room_id = content.get('room_id')
        recipients = content.get('recipients')

        if not room_id or not isinstance(room_id, str):
            logger.warning(
                f'Nostr WS rejected stop_typing — missing/invalid room_id from '
                f'{self.wallet_hash[:16]}...'
            )
            self.close(code=4001)
            return

        if not recipients or not isinstance(recipients, list):
            logger.warning(
                f'Nostr WS rejected stop_typing — missing/invalid recipients from '
                f'{self.wallet_hash[:16]}...'
            )
            self.close(code=4001)
            return

        MAX_RECIPIENTS = 500
        if len(recipients) > MAX_RECIPIENTS:
            logger.warning(
                f'Nostr WS rejected stop_typing — too many recipients '
                f'({len(recipients)}) from {self.wallet_hash[:16]}...'
            )
            self.close(code=4001)
            return

        for pk in recipients:
            if not isinstance(pk, str) or not re.match(r'^[0-9a-fA-F]{64}$', pk):
                logger.warning(
                    f'Nostr WS rejected stop_typing — invalid recipient pubkey '
                    f'from {self.wallet_hash[:16]}...'
                )
                self.close(code=4001)
                return

        normalized_recipients = [pk.lower() for pk in recipients]

        np = NostrPubkey.objects.filter(
            wallet_hash=self.wallet_hash,
        ).values('pubkey_hex').first()

        if not np:
            logger.warning(
                f'Nostr WS stop_typing — no NostrPubkey for wallet '
                f'{self.wallet_hash[:16]}...'
            )
            return

        sender_pubkey = np['pubkey_hex']

        # Clear the typing throttle key so the sender can immediately
        # send a new typing signal without being blocked by the 3s TTL.
        cache = settings.REDISKV
        cache.delete(f'typing:{sender_pubkey}:{room_id}')

        room_map = {
            np_recip['pubkey_hex']: np_recip['wallet_hash']
            for np_recip in NostrPubkey.objects.filter(
                pubkey_hex__in=normalized_recipients,
            ).values('pubkey_hex', 'wallet_hash')
        }

        for recipient_pubkey in normalized_recipients:
            recipient_wallet = room_map.get(recipient_pubkey)
            if recipient_wallet:
                send_stop_typing_update(recipient_wallet, sender_pubkey, room_id)
            else:
                logger.info(
                    f'Nostr WS stop_typing — recipient {recipient_pubkey[:16]}... '
                    f'not found — skipping WS push'
                )

    def typing_update(self, event):
        """Forward a typing indicator to the connected client."""
        from .models import NostrPubkey

        can_see = NostrPubkey.objects.filter(
            wallet_hash=self.wallet_hash,
            show_active_status=True,
        ).exists()
        if not can_see:
            return

        logger.info(
            f'Nostr WS received typing_update for wallet '
            f'{self.wallet_hash[:16]}...: pubkey='
            f'{event.get("pubkey_hex", "")[:16]}... '
            f'room={event.get("room_id", "")[:16]}...'
        )
        self.send(text_data=json.dumps({
            'type': 'typing',
            'pubkey_hex': event['pubkey_hex'],
            'room_id': event['room_id'],
        }))

    def stop_typing_update(self, event):
        """Forward a stop-typing indicator to the connected client."""
        from .models import NostrPubkey

        can_see = NostrPubkey.objects.filter(
            wallet_hash=self.wallet_hash,
            show_active_status=True,
        ).exists()
        if not can_see:
            return

        logger.info(
            f'Nostr WS received stop_typing_update for wallet '
            f'{self.wallet_hash[:16]}...: pubkey='
            f'{event.get("pubkey_hex", "")[:16]}... '
            f'room={event.get("room_id", "")[:16]}...'
        )
        self.send(text_data=json.dumps({
            'type': 'stop_typing',
            'pubkey_hex': event['pubkey_hex'],
            'room_id': event['room_id'],
        }))

    def last_active_update(self, event):
        """Send a last-active timestamp update to the client."""
        from .models import NostrPubkey

        # If the connected user has opted out, don't forward updates.
        can_see = NostrPubkey.objects.filter(
            wallet_hash=self.wallet_hash,
            show_active_status=True,
        ).exists()
        if not can_see:
            return

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
