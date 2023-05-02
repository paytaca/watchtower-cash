from celery import shared_task
from notifications.utils.send import send_push_notification_to_wallet_hashes
from main.models import Address


@shared_task(queue='chat__notifications')
def send_chat_notication(recipient):
    address = Address.objects.get(address=recipient)
    if address.wallet:
        return send_push_notification_to_wallet_hashes(
            [address.wallet.wallet_hash],
            'You received a message'
        )
