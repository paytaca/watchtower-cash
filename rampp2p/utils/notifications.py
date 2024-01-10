from notifications.utils.send import send_push_notification_to_wallet_hashes

import logging
logger = logging.getLogger(__name__)

def send_push_notification(recipients: [], message: str, extra: []):
    logger.warn(f'Sending push notifications | recipients: {recipients} | message: {message} | extra: {extra}')
    notif_title = "Peer-to-Peer Ramp"
    send_push_notification_to_wallet_hashes(
        recipients,
        message,
        title=notif_title,
        extra=extra
    )