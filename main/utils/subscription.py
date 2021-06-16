from main.models import Token,BchAddress, Subscription, SlpAddress, Recipient
from django.conf import settings
from django.db import transaction as trans
from django.db.models import Q
from main.utils.recipient_handler import RecipientHandler
from main.models import (
    Subscription,
    Address
)
from main.tasks import get_slp_utxos, get_bch_utxos
import logging

LOGGER = logging.getLogger(__name__)


def remove_subscription(address, subscriber_id):
    subscription = Subscription.objects.filter(
        address__address=address,
        recipient__telegram_id=subscriber_id
    )
    if subscription.exists():
        subscription.delete()
        return True
    return False


def save_subscription(address, subscriber_id):
    address_obj, _ = Address.objects.get_or_create(address=address)
    recipient, _ = Recipient.objects.get_or_create(telegram_id=subscriber_id)
    subscription, created = Subscription.objects.get_or_create(recipient=recipient, address=address_obj)
    return created


def new_subscription(**kwargs):
    response_template = {'success': False}
    address = kwargs.get('address', None)
    wallet_hash = kwargs.get('wallet_hash', None)
    wallet_index = kwargs.get('wallet_index', None)
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
            
            address_obj, _ = Address.objects.get_or_create(address=address)
            if wallet_hash and wallet_index:
                address_obj.wallet_hash = wallet_hash
                address_obj.wallet_index = wallet_index
                address_obj.save()

            _, created = Subscription.objects.get_or_create(
                recipient=recipient,
                adrress=address_obj
            )

            if address.startswith('simpleledger'):
                get_slp_utxos.delay(address)
            elif address.startswith('bitcoincash'):
                get_bch_utxos.delay(address)

            if created:
                response_template['success'] = True
            else:
                response_template['error'] = 'subscription_already_exists'

    LOGGER.info(response_template)
    return response_template
