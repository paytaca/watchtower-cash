from django.core.cache import cache
from notifications.utils.send import send_push_notification_to_wallet_hashes
from .models import NostrPubkeyDevice

THROTTLE_SECONDS = 30


def send_nostr_push_notification(pubkey_hex):
    """Send a push notification for a Nostr event to all devices linked to a pubkey.

    Reuses the existing push notification infrastructure in notifications.utils.send.
    Throttled to 1 push per pubkey per 30 seconds to avoid spam from read receipts
    and rapid message bursts.
    """
    cache_key = f"nostr_push_throttle:{pubkey_hex}"
    if cache.get(cache_key):
        return
    cache.set(cache_key, True, THROTTLE_SECONDS)

    wallet_hashes = NostrPubkeyDevice.objects.filter(
        pubkey_hex=pubkey_hex,
    ).values_list('wallet_hash', flat=True).distinct()

    if not wallet_hashes:
        return

    # Reuse existing push dispatch — zero new push logic
    send_push_notification_to_wallet_hashes(
        list(wallet_hashes),
        "New message",
        title="New message",
        extra={"type": "nostr_event", "pubkey": pubkey_hex},
    )
