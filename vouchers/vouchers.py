from main.utils.address_converter import bch_address_converter
from main.utils.subscription import new_subscription
from main.utils.queries.node import Node

from paytacapos.models import PosDevice
from vouchers.models import Voucher

from django.conf import settings


def subscribe_vault_address(address):
    project_id = {
        'mainnet': '8feaa0b2-f92e-49fd-a27a-aa6cb23345c7',
        'chipnet': '95ccec69-479a-41c4-90bc-182413ad2f37'
    }
    project_id = project_id[settings.BCH_NETWORK]
    subscription_data = {
        'address': address,
        'project_id': project_id,
    }

    # added try catch here for already subscribed addresses error
    try:
        new_subscription(**subscription_data)
    except:
        pass


def verify_voucher(device_vault_token_address, voucher_ids):
    pos_device = PosDevice.objects.filter(vault__token_address=device_vault_token_address)
    is_device_vault_address = pos_device.exists()
    result = { 'proceed': False }
    
    if is_device_vault_address:
        pos_device = pos_device.first()
        valid_categories = []

        VOUCHER_EXPIRED = 'voucher_expired'
        INVALID_VOUCHER = 'invalid_voucher'
        VOUCHER_MERCHANT_MISMATCH = 'voucher_merchant_mismatch'

        for voucher_id in voucher_ids:
            vouchers = Voucher.objects.filter(id=voucher_id)
            result[voucher_id] = { 'err': '' }

            if vouchers.exists():
                voucher = vouchers.first()

                if pos_device.merchant == voucher.vault.merchant:
                    if voucher.expired:
                        result[voucher_id]['err'] = VOUCHER_EXPIRED
                        return result

                    node = Node()
                    txn = node.BCH.get_transaction(voucher.minting_txid)

                    if txn['valid']:
                        outputs = txn['outputs']
                        key_nft_output = outputs[0]
                        lock_nft_output = outputs[1]

                        lock_nft_recipient = lock_nft_output['address']
                        lock_nft_recipient = bch_address_converter(lock_nft_recipient)
                        key_nft_category = key_nft_output['token_data']['category']
                        
                        if key_nft_category == voucher.category:
                            valid_categories.append(key_nft_category)
                        else:
                            result[voucher_id]['err'] = VOUCHER_MERCHANT_MISMATCH
                    else:
                        result[voucher_id]['err'] = INVALID_VOUCHER
                else:
                    result[voucher_id]['err'] = VOUCHER_MERCHANT_MISMATCH
            else:
                result[voucher_id]['err'] = INVALID_VOUCHER

        if len(valid_categories) == len(voucher_ids):
            result['proceed'] = True

    return result