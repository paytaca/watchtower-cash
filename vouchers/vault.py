from django.conf import settings

from paytacapos.models import Merchant

from vouchers.js.runner import ScriptFunctions
from vouchers.models import Vault, Voucher

from main.utils.subscription import new_subscription


def generate_merchant_vault(merchant_id):
    merchant = Merchant.objects.get(id=merchant_id)
    if not merchant.receiving_pubkey:
        return

    receiving_pubkey = merchant.receiving_pubkey

    contract = ScriptFunctions.compileVaultContract(dict(
        params=dict(
            merchant={
                'receiverPk': receiving_pubkey
            }
        ),
        options=dict(network=settings.BCH_NETWORK)
    ))

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
    Vault.objects.filter(merchant=merchant).delete()

    Vault(
        merchant=merchant,
        address=contract['address'],
        token_address=contract['tokenAddress']
    ).save()
