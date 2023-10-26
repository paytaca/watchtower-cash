from notifications.utils.send import send_push_notification_to_wallet_hashes

def send_push_notification(recipients: [], message: str, extra: []):
    notif_title = "Peer-to-Peer Ramp"
    send_push_notification_to_wallet_hashes(
        recipients,
        message,
        title=notif_title,
        extra=extra
    )