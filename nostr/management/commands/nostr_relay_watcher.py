import json
import time
import logging
import websocket
from django.core.management.base import BaseCommand
from django.db import connection
from nostr.utils import send_nostr_push_notification
from nostr.models import NostrPubkey

logger = logging.getLogger(__name__)

RELAY_URL = "wss://relay.paytaca.com"
SUBSCRIPTION_KINDS = [1059]
PUBKEY_REFRESH_INTERVAL = 60  # seconds


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
                time.sleep(5)

    def run_watcher(self, relay_url):
        pubkeys = self.get_registered_pubkeys()
        if not pubkeys:
            logger.info("No registered pubkeys, waiting...")
            time.sleep(PUBKEY_REFRESH_INTERVAL)
            return

        logger.info(f"Connecting to {relay_url}")
        ws = websocket.create_connection(relay_url, timeout=5)

        sub_id = "watchtower-push"
        req = [
            "REQ",
            sub_id,
            {
                "kinds": SUBSCRIPTION_KINDS,
                "#p": pubkeys,
            },
        ]
        ws.send(json.dumps(req))
        logger.info(f"Subscribed to {len(pubkeys)} pubkeys")

        last_pubkey_refresh = time.time()

        while True:
            try:
                # Check if we need to refresh the pubkey list
                if time.time() - last_pubkey_refresh > PUBKEY_REFRESH_INTERVAL:
                    new_pubkeys = self.get_registered_pubkeys()
                    if set(new_pubkeys) != set(pubkeys):
                        logger.info("Pubkey list changed, reconnecting...")
                        ws.close()
                        return
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
                    for tag in event.get("tags", []):
                        if isinstance(tag, list) and len(tag) >= 2 and tag[0] == "p":
                            recipient_pubkey = tag[1]
                            if recipient_pubkey in pubkeys:
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
