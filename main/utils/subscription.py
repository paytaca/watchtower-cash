from main.models import Token, Subscription, Recipient
from django.conf import settings
from django.db import transaction as trans
from django.db.models import Q
from main.utils.recipient_handler import RecipientHandler
from main.models import (
    Subscription,
    Address,
    Project,
    Wallet
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
    response = {'success': False}
    address = kwargs.get('address', None)
    project_id = kwargs.get('project_id', None)
    wallet_hash = kwargs.get('wallet_hash', None)
    wallet_index = kwargs.get('wallet_index', None)
    web_url = kwargs.get('webhook_url', None)
    telegram_id = kwargs.get('telegram_id', None)
    if address is not None:
        address = address.lower()
        if address.startswith('bitcoincash:') or address.startswith('simpleledger:'):
            proceed = False
            if project_id:
                project_check = Project.objects.filter(id=project_id)
                if project_check.exists():
                    project = project_check.first()
                    proceed = True
                else:
                    response['error'] = 'project_does_not_exist'
            else:
                proceed = True
            
            if proceed:
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
                if wallet_hash is not None and wallet_index is not None:
                    wallet, _ = Wallet.objects.get_or_create(
                        wallet_hash=wallet_hash,
                        project=project
                    )
                    address_obj.wallet = wallet
                    address_obj.wallet_index = wallet_index
                    address_obj.project = project
                    address_obj.save()

                _, created = Subscription.objects.get_or_create(
                    recipient=recipient,
                    address=address_obj
                )

                if address.startswith('simpleledger'):
                    get_slp_utxos.delay(address)
                elif address.startswith('bitcoincash'):
                    get_bch_utxos.delay(address)

                if created:
                    response['success'] = True
                else:
                    response['error'] = 'subscription_already_exists'
        else:
            response['error'] = 'invalid_address'

    LOGGER.info(response)
    return response
