import datetime
import logging

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


logger = logging.getLogger(__name__)


def send_last_active_update(wallet_hash, pubkey_hex, timestamp):
    """Push a last-active update to all clients connected for this wallet.

    The WebSocket group is keyed by wallet_hash so that any client watching
    that wallet receives real-time notifications when the nostr pubkey's
    last-active timestamp changes.

    Skips the push if the sender's ``show_active_status`` is False (they're
    invisible) or if the recipient's ``show_active_status`` is False (they
    can't see others' status).
    """
    from nostr.models import NostrPubkey

    sender_visible = NostrPubkey.objects.filter(
        pubkey_hex=pubkey_hex,
        show_active_status=True,
    ).exists()
    if not sender_visible:
        logger.info(
            f'Skipping WS push — sender pubkey {pubkey_hex[:16]}... '
            f'has show_active_status=False or not found'
        )
        return

    recipient_can_see = NostrPubkey.objects.filter(
        wallet_hash=wallet_hash,
        show_active_status=True,
    ).exists()
    if not recipient_can_see:
        logger.info(
            f'Skipping WS push — recipient wallet {wallet_hash[:16]}... '
            f'has show_active_status=False or not found'
        )
        return

    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning(
            f'No channel layer configured — cannot send last_active '
            f'update for wallet {wallet_hash}'
        )
        return

    room_group_name = f'nostr_updates_{wallet_hash}'

    if isinstance(timestamp, datetime.datetime):
        timestamp = timestamp.isoformat().replace('+00:00', 'Z')

    try:
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'last_active_update',
                'pubkey_hex': pubkey_hex,
                'timestamp': str(timestamp),
            },
        )
        logger.info(
            f'Sent last_active WS update for wallet {wallet_hash}, '
            f'pubkey {pubkey_hex[:16]}...'
        )
    except Exception as e:
        logger.error(
            f'Failed to send last_active WS update for wallet '
            f'{wallet_hash}: {e}'
        )

