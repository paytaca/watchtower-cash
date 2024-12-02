from notifications.utils.send import send_push_notification_to_wallet_hashes
from main.utils.broadcast import broadcast_to_engagementhub
from django.utils import timezone

import logging
logger = logging.getLogger(__name__)

def send_push_notification(recipients: list, message: str, extra: list):
    logger.warning(f'Sending push notifications | recipients: {recipients} | message: {message} | extra: {extra}')
    notif_title = "P2P Exchange"
    send_push_notification_to_wallet_hashes(
        recipients,
        message,
        title=notif_title,
        extra=extra
    )

    broadcast_to_engagementhub({
        'title': notif_title,
        'message': message,
        'wallet_hash': recipients,
        'notif_type': 'RP',
        'date_posted': timezone.now().isoformat()
    })