from django.conf import settings

from paytacapos.models import Merchant
from vouchers.models import Vault
from main.utils.subscription import new_subscription

import requests


def generate_voucher_vault(pos_device_id, pubkey):
    pos_device = PosDevice.objects.get(id=pos_device_id)

    if not pubkey:
        return

    payload = {
        'params': {
            'merchant': {
                'receiverPk': pubkey
            }
        },
        'options': {
            'network': settings.BCH_NETWORK
        }
    }
    response = requests.post(f'{settings.VOUCHER_EXPRESS_URL}/compile-vault', json=payload)
    contract = response.json()

    # subscribe merchant vault address
    project_id = {
        'mainnet': '8feaa0b2-f92e-49fd-a27a-aa6cb23345c7',
        'chipnet': '95ccec69-479a-41c4-90bc-182413ad2f37'
    }
    project_id = project_id[settings.BCH_NETWORK]

    subscription_data = {
        'address': contract['address'],
        'project_id': project_id,
    }

    # added try catch here for already subscribed addresses error
    try:
        new_subscription(**subscription_data)
    except:
        pass

    # delete existing old vault
    Vault.objects.filter(pos_device=pos_device).delete()

    Vault(
        pos_device=pos_device,
        pubkey=pubkey,
        address=contract['address'],
        token_address=contract['tokenAddress']
    ).save()
