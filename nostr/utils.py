import logging
from django.core.cache import cache
from notifications.utils.send import send_push_notification_to_wallet_hashes
from .models import NostrPubkeyDevice

logger = logging.getLogger(__name__)
THROTTLE_SECONDS = 30


def send_nostr_push_notification(pubkey_hex):
    """Send a push notification for a Nostr event to all devices linked to a pubkey.

    Reuses the existing push notification infrastructure in notifications.utils.send.
    Throttled to 1 push per pubkey per 30 seconds to avoid spam from read receipts
    and rapid message bursts.
    """
    cache_key = f"nostr_push_throttle:{pubkey_hex}"
    if cache.get(cache_key):
        logger.info(f"Push throttled for pubkey {pubkey_hex[:16]}...")
        return
    cache.set(cache_key, True, THROTTLE_SECONDS)

    wallet_hashes = list(NostrPubkeyDevice.objects.filter(
        pubkey_hex=pubkey_hex,
    ).values_list('wallet_hash', flat=True).distinct())

    logger.info(f"Found wallet hashes for pubkey {pubkey_hex[:16]}...: {wallet_hashes}")

    if not wallet_hashes:
        logger.warning(f"No wallet hashes found for pubkey {pubkey_hex[:16]}...")
        return

    # Reuse existing push dispatch — zero new push logic
    logger.info(f"Sending push to wallet hashes: {wallet_hashes}")
    try:
        gcm_response, apns_response = send_push_notification_to_wallet_hashes(
            wallet_hashes,
            "You have received a new message",
            title="Chat",
            extra={"type": "nostr_event", "pubkey": pubkey_hex},
        )
        logger.info(f"Push send complete. GCM: {gcm_response}, APNS: {apns_response}")
    except Exception as e:
        logger.exception(f"Push send failed with exception: {e}")
