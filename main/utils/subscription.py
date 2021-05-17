from main.models import BchAddress, Subscription, SlpAddress, Recipient
from django.conf import settings
from django.db import transaction as trans
from django.db.models import Q

def remove_subscription(address, subscriber_id):
    subscription = Subscription.objects.filter(
        Q(slp__address=(address)) | Q(bch__address=(address)),
        recipient__telegram_id=subscriber_id
    )
    if subscription.exists():
        subscription.delete()
        return True
    return False

def save_subscription(address, subscriber_id):
    
    subscriber = None

    destination_address = None

    if address.startswith('bitcoincash'):
        bch, created = BchAddress.objects.get_or_create(address=address)
        slp = None
        
    
    if address.startswith('simpleledger'):
        slp, created = SlpAddress.objects.get_or_create(address=address)
        bch = None

    recipient, _ = Recipient.objects.get_or_create(telegram_id=subscriber_id)
    subscription, created = Subscription.objects.get_or_create(recipient=recipient,slp=slp,bch=bch)
    
    return created

