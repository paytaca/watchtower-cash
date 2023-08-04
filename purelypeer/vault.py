from django.conf import settings

from paytacapos.models import Merchant

from purelypeer.js.runner import ScriptFunctions
from purelypeer.models import Vault

from main.models import Address


def generate_merchant_vault(merchant_id):
    merchant = Merchant.objects.get(id=merchant_id)

    # latest bch address of merchant wallet
    merchant_receiving_address = Address.objects.filter(
        wallet__wallet_hash=merchant.wallet_hash,
        wallet__wallet_type='bch'
    ).order_by('id').last()

    address = merchant_receiving_address.address

    receiving_pubkey = ScriptFunctions.cashAddrToPubkey(dict(address=address))
    receiving_pubkey_hash = ScriptFunctions.cashAddrToPubkey(dict(
        address=address,
        hash=True,
        toString=True
    ))
    contract = ScriptFunctions.compileVaultContract(dict(
        params=dict(merchantPkHash=receiving_pubkey_hash),
        options=dict(network=settings.BCH_NETWORK)
    ))

    Vault(
        merchant=merchant,
        address=contract['address'],
        token_address=contract['tokenAddress'],
        receiving_pubkey=receiving_pubkey,
        receiving_pubkey_hash=receiving_pubkey_hash
    ).save()
