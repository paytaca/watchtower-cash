from paytacapos.models import PosDevice
from vouchers.models import Voucher


def verify_voucher(vault_token_address, voucher_ids):
    pos_device = PosDevice.objects.filter(vault__token_address=vault_token_address)
    is_vault_address = pos_device.exists()
    result = { 'proceed': False }
    
    if is_vault_address:
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

                if pos_device.vault == voucher.vault:
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

                        # check if lock NFT recipient address is this endpoint payload's vault address
                        if key_nft_category == voucher.category and lock_nft_recipient == vault_token_address:
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