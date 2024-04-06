from notifications.utils.send import send_push_notification_to_wallet_hashes

import logging
logger = logging.getLogger(__name__)

def send_push_notification(recipients: list, message: str, extra: list):
    logger.warn(f'Sending push notifications | recipients: {recipients} | message: {message} | extra: {extra}')
    notif_title = "P2P Exchange"
    send_push_notification_to_wallet_hashes(
        recipients,
        message,
        title=notif_title,
        extra=extra
    )