import hashlib
import hmac
import logging

from django.conf import settings


logger = logging.getLogger(__name__)

# Outer gift-wrap tag carrying the opaque push token for the conversation. The
# token is what lets the relay watcher attribute a NIP-17 gift-wrap to a room
# without exposing the room id or its members.
#
# Trust model: anyone may put any token on a gift-wrap. The tag is only used to
# subtract recipients that already muted (or archived) that token, so a spoofed
# value can never add recipients or reveal anything about a room. At worst it
# fails to suppress one push or suppresses one push the muter asked to skip.
ROOM_PUSH_TOKEN_TAG = "paytaca-room"
ROOM_CACHE_DIRTY_KEY = "nostr:room_cache:dirty"


def room_push_token(room_id):
    """Return the opaque push token for a room.

    Derived from the room id so every member's row for the same room gets the
    same token without storing another column. The HMAC key keeps the relay
    from recomputing it from a guessed room id.
    """
    message = f"nostr-room-push:{room_id}".encode()
    return hmac.new(
        settings.SECRET_KEY.encode(),
        message,
        hashlib.sha256,
    ).hexdigest()


def mark_room_cache_dirty():
    """Tell the relay watcher to rebuild its room caches on the next tick.

    The watcher refreshes them every minute anyway; this makes a mute or
    membership change effective as soon as the next event arrives.
    """
    client = getattr(settings, "REDISKV", None)
    if client is None:
        return
    try:
        client.set(ROOM_CACHE_DIRTY_KEY, "1", ex=3600)
    except Exception as e:
        logger.warning(f"Failed to mark nostr room cache dirty: {e}")
