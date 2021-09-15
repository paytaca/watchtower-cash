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
    addresses = kwargs.get('addresses', None)
    project_id = kwargs.get('project_id', None)
    wallet_hash = kwargs.get('wallet_hash', None)
    # `wallet_index` is kept for backward-compatibility with v1 wallets
    wallet_index = kwargs.get('wallet_index', None)
    address_index = kwargs.get('address_index', None)
    web_url = kwargs.get('webhook_url', None)
    telegram_id = kwargs.get('telegram_id', None)
    if address or addresses:
        address_list = []
        if isinstance(address, str):
            address_list.append([address.strip(), wallet_index])
        elif isinstance(addresses, dict):
            address_list.append([addresses['receiving'], '0/' + str(address_index)])
            if 'change' in addresses.keys():
                address_list.append([addresses['change'], '1/' + str(address_index)])
        for address, path in address_list:
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
                    if wallet_hash:
                        if wallet_index is not None or address_index is not None:
                            if isinstance(path, str):
                                if '/' in path:
                                    address_obj.address_path = path
                                    wallet_version = 2
                            else:
                                # Deal with subscription for v1 wallets
                                address_obj.wallet_index = int(path)
                                address_obj.address_path = path
                                wallet_version = 1
                            wallet_check = Wallet.objects.filter(
                                wallet_hash=wallet_hash
                            )
                            if wallet_check.exists():
                                wallet = wallet_check.last()
                            else:
                                wallet = Wallet(
                                    wallet_hash=wallet_hash,
                                    version=wallet_version
                                )
                                wallet.save()
                            if wallet.version != wallet_version:
                                wallet.version = wallet_version
                                wallet.save()
                            if not wallet.project:
                                wallet.project = project
                                wallet.save()
                            address_obj.wallet = wallet
                            address_obj.save()

                    _, created = Subscription.objects.get_or_create(
                        recipient=recipient,
                        address=address_obj
                    )

                    if address.startswith('simpleledger'):
                        get_slp_utxos.delay(address)
                    elif address.startswith('bitcoincash'):
                        get_bch_utxos.delay(address)

                    response['success'] = True
            else:
                response['error'] = 'invalid_address'

    LOGGER.info(response)
    return response
