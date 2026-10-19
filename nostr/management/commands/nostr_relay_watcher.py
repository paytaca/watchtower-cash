import json
import time
import logging
import websocket
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings
from nostr.utils import send_nostr_push_notification
from nostr.models import NostrPubkey, NostrRoom


logger = logging.getLogger(__name__)

RELAY_URL = "wss://relay.paytaca.com"
GIFT_WRAP_KIND = 1059
GROUP_EVENT_KIND = 445  # NIP-EE MLS group message
SUBSCRIPTION_KINDS = [GIFT_WRAP_KIND, GROUP_EVENT_KIND]
PUBKEY_REFRESH_INTERVAL = 60  # seconds
SEEN_EVENT_TTL = 60 * 60 * 24  # 24 hours — how long to remember processed event IDs
RECONNECT_DELAY = 5  # seconds to wait before reconnecting
EOSE_TIMEOUT = 30  # seconds to wait for EOSE before processing events anyway


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

    def _refresh_group_cache(self):
        """Rebuild the in-memory ``nostr_group_id -> {member pubkey hex}`` lookup.

        Called every ``PUBKEY_REFRESH_INTERVAL`` seconds so the hot path never
        hits Postgres per event. Archived rooms are excluded so that a wallet
        deleting a group stops forcing pushes immediately. Membership of each
        room row is unioned because each member has their own row keyed by
        ``room_id`` (which is per-wallet) but shared ``nostr_group_id``.
        """
        try:
            connection.ensure_connection()
            rows = NostrRoom.objects.filter(
                nostr_group_id__isnull=False,
                archived=False,
            ).values_list('nostr_group_id', 'members')
        except Exception as e:
            logger.error(f"Failed to refresh group cache: {e}")
            self._group_members_cache = {}
            return

        new_cache = {}
        for nostr_group_id, members in rows:
            if not isinstance(members, list):
                logger.warning(
                    f"NostrRoom nostr_group_id={nostr_group_id[:16]}... has "
                    f"non-list members field (type={type(members).__name__}); "
                    "skipping from group cache"
                )
                continue
            recipients = new_cache.setdefault(nostr_group_id, set())
            for m in members:
                if isinstance(m, str):
                    recipients.add(m)
        self._group_members_cache = new_cache

    def run_watcher(self, relay_url):
        # Obtain the shared Redis client configured in settings
        redis_client = getattr(settings, "REDISKV", None)
        if redis_client is None:
            logger.warning("REDISKV not configured — event deduplication disabled")

        # Prime the in-memory lookups once before opening the socket so the
        # first few events don't hit the DB.
        self._group_members_cache = {}
        self._refresh_group_cache()

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
        logger.info(
            f"Subscribed to kinds {SUBSCRIPTION_KINDS} "
            "(pubkey filtering done client-side)"
        )

        last_pubkey_refresh = time.time()
        has_seen_eose = False
        connected_at = time.time()

        while True:
            try:
                # Refresh the registered pubkeys and group cache periodically
                # so newly registered wallets and any room-list changes
                # (members, archive) take effect without per-event DB queries.
                if time.time() - last_pubkey_refresh > PUBKEY_REFRESH_INTERVAL:
                    pubkeys = set(self.get_registered_pubkeys())
                    self._refresh_group_cache()
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
                    # Skip all stored events replayed before EOSE, with a
                    # fallback: if EOSE hasn't arrived within EOSE_TIMEOUT
                    # seconds, start processing anyway.
                    if not has_seen_eose and time.time() - connected_at < EOSE_TIMEOUT:
                        continue

                    event = msg[2]
                    if not isinstance(event, dict):
                        continue
                    event_id = event.get("id")
                    if not event_id:
                        continue

                    # Deduplicate: skip events we have already processed.
                    # This guards against relay re-delivery and reconnect replays.
                    if redis_client is not None and self._is_seen_event(redis_client, event_id):
                        logger.info(f"Skipping already-seen event {event_id}")
                        continue

                    # Skip events that should not trigger push notifications.
                    # nonotif/read-receipt tags are placed on the outer gift-wrap by the
                    # sender so they are visible here without decrypting the inner event.
                    event_tags = event.get("tags", [])
                    if any(
                        isinstance(t, list) and len(t) >= 1 and t[0] in ("nonotif", "self")
                        for t in event_tags
                    ):
                        continue

                    event_kind = event.get("kind")

                    if event_kind == GROUP_EVENT_KIND:
                        # NIP-EE MLS group messages are signed with an ephemeral
                        # key and carry only an "h" tag (the public
                        # nostr_group_id), so the sender cannot be identified
                        # here. Resolve recipients from the room -> member
                        # mapping the client registered via /api/nostr/rooms/.
                        h_tag = next(
                            (
                                tag[1]
                                for tag in event_tags
                                if isinstance(tag, list) and len(tag) >= 2 and tag[0] == "h"
                            ),
                            None,
                        )
                        recipient_pubkeys = (
                            self.get_group_recipient_pubkeys(h_tag, pubkeys)
                            if h_tag else set()
                        )
                    else:
                        # Gift-wraps (kind 1059) address recipients via "p" tags.
                        # Collect unique recipient pubkeys to avoid sending
                        # duplicate notifications when a pubkey appears more than
                        # once. Exclude self-sends (event pubkey == recipient).
                        event_pubkey = event.get("pubkey", "")
                        recipient_pubkeys = {
                            tag[1]
                            for tag in event_tags
                            if isinstance(tag, list) and len(tag) >= 2
                            and tag[0] == "p"
                            and tag[1] in pubkeys
                            and tag[1] != event_pubkey
                        }

                    now = timezone.now()

                    # Update recipients' last_active — receiving a gift-wrap
                    # means they were online at this point. Group events are
                    # excluded: bumping every member on each message would make
                    # the whole group appear permanently online.
                    #
                    # Known v1 gap: this excludes every group event, so MLS
                    # users that only ever appear in groups won't get their
                    # last_active refreshed here. A self-tagged pubkey or a
                    # periodic ping would close the gap — left for v2 since
                    # group-member push behavior is the dominant use case.
                    if recipient_pubkeys and event_kind != GROUP_EVENT_KIND:
                        NostrPubkey.objects.filter(
                            pubkey_hex__in=recipient_pubkeys,
                            show_active_status=True,
                        ).update(last_active=now)

                    for recipient_pubkey in recipient_pubkeys:
                        logger.info(f"Detected event {event_id} (kind {event_kind}) for pubkey {recipient_pubkey[:16]}... sending push")
                        send_nostr_push_notification(recipient_pubkey)

                elif msg_type == "EOSE":
                    logger.info("End of stored events — now processing live events")
                    has_seen_eose = True

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

    def get_group_recipient_pubkeys(self, nostr_group_id, registered_pubkeys):
        """Resolve recipient pubkeys for a NIP-EE MLS group event (kind 445).

        Reads from the in-memory cache populated by ``_refresh_group_cache``
        rather than the DB. The cache is rebuilt every ``PUBKEY_REFRESH_INTERVAL``
        seconds. Group events carry only the public ``h`` tag
        (``nostr_group_id``) and are signed with an ephemeral key, so recipients
        cannot be read from the event itself — the client registers each group
        room (with its member list) via ``/api/nostr/rooms/``, and the cache
        unions the member lists of every room row sharing this group id while
        intersecting with currently registered pubkeys.
        """
        if not nostr_group_id:
            return set()
        members = self._group_members_cache.get(nostr_group_id)
        if members is None:
            return set()
        return members & registered_pubkeys
