import json
import time
import logging
import websocket
from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings
from nostr.utils import send_nostr_push_notification
from nostr.models import NostrPubkey

logger = logging.getLogger(__name__)

RELAY_URL = "wss://relay.paytaca.com"
SUBSCRIPTION_KINDS = [1059]
PUBKEY_REFRESH_INTERVAL = 60  # seconds
SEEN_EVENT_TTL = 60 * 60 * 24  # 24 hours — how long to remember processed event IDs
RECONNECT_DELAY = 5  # seconds to wait before reconnecting


class Command(BaseCommand):
    help = "Watch Nostr relay for gift-wraps and send push notifications"

    def add_arguments(self, parser):
        parser.add_argument(
            '--relay',
            type=str,
            default=RELAY_URL,
            help='Nostr relay WebSocket URL',
        )

    def handle(self, *args, **options):
        if settings.BCH_NETWORK != 'mainnet':
            logger.info(f"Nostr relay watcher is disabled on {settings.BCH_NETWORK}, exiting.")
            return

        relay_url = options['relay']
        logger.info(f"Starting Nostr relay watcher for {relay_url}")

        while True:
            try:
                self.run_watcher(relay_url)
            except KeyboardInterrupt:
                logger.info("Watcher stopped by user")
                break
            except Exception as e:
                logger.error(f"Watcher crashed: {e}")
            # Always wait before reconnecting to avoid hammering the relay
            # and replaying stored events in a tight loop
            logger.info(f"Reconnecting in {RECONNECT_DELAY}s...")
            time.sleep(RECONNECT_DELAY)

    def _is_seen_event(self, redis_client, event_id):
        """Return True if this event ID has already been processed.

        Uses a Redis key with a 24-hour TTL so the seen-set doesn't grow forever.
        Uses SETNX (set-if-not-exists) so the check and mark are atomic.
        """
        key = f"nostr_seen_event:{event_id}"
        # SET key 1 EX ttl NX — returns True if key was set (first time seen)
        result = redis_client.set(key, 1, ex=SEEN_EVENT_TTL, nx=True)
        return result is None  # None means key already existed → already seen

    def run_watcher(self, relay_url):
        # Obtain the shared Redis client configured in settings
        redis_client = getattr(settings, "REDISKV", None)
        if redis_client is None:
            logger.warning("REDISKV not configured — event deduplication disabled")

        pubkeys = set(self.get_registered_pubkeys())
        if not pubkeys:
            logger.info("No registered pubkeys, waiting...")
            time.sleep(PUBKEY_REFRESH_INTERVAL)
            return

        logger.info(f"Connecting to {relay_url}")
        ws = websocket.create_connection(
            relay_url,
            timeout=5,
            ping_interval=30,
            ping_timeout=10,
        )

        sub_id = "watchtower-push"
        req = [
            "REQ",
            sub_id,
            {"kinds": SUBSCRIPTION_KINDS},
        ]
        ws.send(json.dumps(req))
        logger.info("Subscribed to all kind-1059 events (pubkey filtering done client-side)")

        last_pubkey_refresh = time.time()

        while True:
            try:
                # Refresh the registered pubkey set periodically
                if time.time() - last_pubkey_refresh > PUBKEY_REFRESH_INTERVAL:
                    pubkeys = set(self.get_registered_pubkeys())
                    last_pubkey_refresh = time.time()

                # Receive with timeout so we can refresh pubkeys periodically
                msg_raw = ws.recv()
                if not msg_raw:
                    continue

                msg = json.loads(msg_raw)

                if not isinstance(msg, list) or len(msg) < 2:
                    continue

                msg_type = msg[0]

                if msg_type == "EVENT" and len(msg) >= 3:
                    event = msg[2]
                    if not isinstance(event, dict):
                        continue
                    event_id = event.get("id", "unknown")

                    # Deduplicate: skip events we have already processed.
                    # This guards against relay re-delivery and reconnect replays.
                    if redis_client is not None and self._is_seen_event(redis_client, event_id):
                        logger.info(f"Skipping already-seen event {event_id}")
                        continue

                    # Skip events that should not trigger push notifications
                    event_tags = event.get("tags", [])
                    if any(
                        isinstance(t, list) and len(t) >= 1 and t[0] in ("nonotif", "self")
                        for t in event_tags
                    ):
                        continue

                    # Collect unique recipient pubkeys from all "p" tags to avoid
                    # sending duplicate notifications when a pubkey appears more than once
                    recipient_pubkeys = {
                        tag[1]
                        for tag in event_tags
                        if isinstance(tag, list) and len(tag) >= 2 and tag[0] == "p" and tag[1] in pubkeys
                    }

                    for recipient_pubkey in recipient_pubkeys:
                        logger.info(f"Detected gift-wrap event {event_id} for pubkey {recipient_pubkey[:16]}... sending push")
                        send_nostr_push_notification(recipient_pubkey)

                elif msg_type == "EOSE":
                    logger.info("End of stored events")

                elif msg_type == "CLOSED":
                    reason = msg[2] if len(msg) >= 3 else "unknown"
                    logger.warning(f"Subscription closed: {reason}")
                    ws.close()
                    return

            except websocket.WebSocketTimeoutException:
                # Timeout is expected — loop around to check pubkey refresh
                continue
            except websocket.WebSocketConnectionClosedException:
                logger.warning("WebSocket closed, reconnecting...")
                return
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                time.sleep(1)

    def get_registered_pubkeys(self):
        """Fetch all distinct pubkeys from the NostrPubkey registry."""
        try:
            # Ensure fresh connection in case DB was idle
            connection.ensure_connection()
            return list(
                NostrPubkey.objects.values_list('pubkey_hex', flat=True).distinct()
            )
        except Exception as e:
            logger.error(f"Failed to fetch pubkeys: {e}")
            return []
