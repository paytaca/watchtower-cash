from django.conf import settings

from paytacapos.models import Merchant

from purelypeer.js.runner import ScriptFunctions
from purelypeer.models import Vault, CashdropNftPair

from main.utils.subscription import new_subscription
from main.models import Address


def generate_merchant_vault(merchant_id):
    merchant = Merchant.objects.get(id=merchant_id)
    merchant_receiving_address = Address.objects.filter(
        wallet__wallet_hash=merchant.wallet_hash,
        wallet__wallet_type='bch',
        address_path='0/0'
    ).first()

    address = merchant_receiving_address.address
    receiving_pubkey = ScriptFunctions.cashAddrToPubkey(dict(address=address))
    receiving_pubkey_hash = ScriptFunctions.cashAddrToPubkey(dict(
        address=address,
        hash=True,
        toString=True
    ))
    contract = ScriptFunctions.compileVaultContract(dict(
        params=dict(merchantPk=receiving_pubkey),
        options=dict(network=settings.BCH_NETWORK)
    ))

    # subscribe merchant address
    project_id = '8feaa0b2-f92e-49fd-a27a-aa6cb23345c7'
    if settings.BCH_NETWORK == 'chipnet':
        project_id = '95ccec69-479a-41c4-90bc-182413ad2f37'

    subscription_data = {
        'address': contract['address'],
        'project_id': project_id,
    }
    new_subscription(**subscription_data)

    Vault(
        merchant=merchant,
        address=contract['address'],
        token_address=contract['tokenAddress'],
        merchant_receiving_address=address,
        receiving_pubkey=receiving_pubkey,
        receiving_pubkey_hash=receiving_pubkey_hash
    ).save()
