from main.models import Token,BchAddress, Subscription, SlpAddress, Recipient
from django.conf import settings
from django.db import transaction as trans
from django.db.models import Q
from main.utils.recipient_handler import RecipientHandler
from main.models import (
    Subscription,
    SlpAddress,
    BchAddress
)
from main.tasks import LOGGER, get_slp_utxos, get_bch_utxos
import logging
LOOGER = logging.getLogger(__name__)

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


def new_subscription(**kwargs):
    response_template = {'success': False}
    address = kwargs.get('address', None)
    web_url = kwargs.get('webhook_url', None)
    telegram_id = kwargs.get('telegram_id', None)
    if address is not None:
        address = address.lower()
        if address.startswith('bitcoincash:') or address.startswith('simpleledger:'):
            obj_recipient = RecipientHandler(
                web_url=web_url,
                telegram_id=telegram_id
            )
            recipient, created = obj_recipient.get_or_create()
                            
            if recipient and not created:
                # Renew validity.
                recipient.valid = True
                recipient.save()     
                
            bch = None
            slp = None

            if address.startswith('simpleledger'):
                slp, _ = SlpAddress.objects.get_or_create(address=address)
                
            elif address.startswith('bitcoincash'):
                bch, _ = BchAddress.objects.get_or_create(address=address)
            
            _, created = Subscription.objects.get_or_create(
                recipient=recipient,
                slp=slp,
                bch=bch
            )
            if bch:
                get_bch_utxos.delay(address)
            
            if slp:
                get_slp_utxos.delay(address)

            if created:
                response_template['success'] = True
            else:
                response_template['error'] = 'subscription_already_exists'
    LOOGER.info(response_template)
    return response_template
