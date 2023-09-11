from django.conf import settings

from paytacapos.models import Merchant

from vouchers.js.runner import ScriptFunctions
from vouchers.models import Vault, Voucher

from main.utils.subscription import new_subscription
from main.models import Address


def generate_merchant_vault(merchant_id):
    merchant = Merchant.objects.get(id=merchant_id)
    merchant_receiving_address = Address.objects.filter(
        wallet__wallet_hash=merchant.wallet_hash,
        wallet__wallet_type='bch',
        address_path='0/0'
    )

    if not merchant_receiving_address.exists():
        return

    receiving_pubkey = merchant.receiving_pubkey
    signer_pubkey = merchant.signer_pubkey

    contract = ScriptFunctions.compileVaultContract(dict(
        params=dict(
            merchantReceiverPk=receiving_pubkey,
            merchantSignerPk=signer_pubkey
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

    Vault(
        merchant=merchant,
        address=contract['address'],
        token_address=contract['tokenAddress']
    ).save()
