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
    )
    merchant_signer_address = Address.objects.filter(
        wallet__wallet_hash=merchant.signer_wallet_hash,
        wallet__wallet_type='bch',
        address_path='0/0'
    )

    if not merchant_signer_address.exists() and not merchant_receiving_address.exists():
        return
    
    merchant_receiving_address = merchant_receiving_address.first()
    merchant_signer_address = merchant_signer_address.first()
    address = merchant_receiving_address.address
    signer_address = merchant_signer_address.address

    receiving_pubkey = ScriptFunctions.cashAddrToPubkey(dict(address=address))
    signer_pubkey = ScriptFunctions.cashAddrToPubkey(dict(address=signer_address))

    receiving_pubkey_hash = ScriptFunctions.cashAddrToPubkey(dict(
        address=address,
        hash=True,
        toString=True
    ))
    signer_pubkey_hash = ScriptFunctions.cashAddrToPubkey(dict(
        address=signer_address,
        hash=True,
        toString=True
    ))

    contract = ScriptFunctions.compileVaultContract(dict(
        params=dict(
            merchantReceiverPk=receiving_pubkey,
            merchantSignerPk=signer_pubkey
        ),
        options=dict(network=settings.BCH_NETWORK)
    ))

    # subscribe merchant address
    project_id = {
        'mainnet': '8feaa0b2-f92e-49fd-a27a-aa6cb23345c7',
        'chipnet': '95ccec69-479a-41c4-90bc-182413ad2f37'
    }
    project_id = project_id[settings.BCH_NETWORK]

    subscription_data = {
        'address': contract['address'],
        'project_id': project_id,
    }
    new_subscription(**subscription_data)

    Merchant.objects.filter(id=merchant_id).update(
        receiving_address=address,
        signer_address=signer_address,
        receiving_pubkey=receiving_pubkey,
        receiving_pubkey_hash=receiving_pubkey_hash,
        signer_pubkey=signer_pubkey,
        signer_pubkey_hash=signer_pubkey_hash
    )

    Vault(
        merchant=merchant,
        address=contract['address'],
        token_address=contract['tokenAddress']
    ).save()
