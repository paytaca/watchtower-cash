from main.models import Transaction
from django.db.models import Sum
from django.conf import settings


class HistoryParser(object):

    def __init__(self, txid, wallet_hash):
        self.txid = txid
        self.wallet_hash = wallet_hash

    def get_relevant_inputs(self):
        inputs = Transaction.objects.filter(
            spending_txid=self.txid,
            address__wallet__wallet_hash=self.wallet_hash
        ).exclude(
            txid=self.txid
        ).exclude(
            token__tokenid=settings.WT_DEFAULT_CASHTOKEN_ID
        )
        ct_fungible_inputs = Transaction.objects.filter(
            spending_txid=self.txid,
            address__wallet__wallet_hash=self.wallet_hash,
            cashtoken_ft__isnull=False
        )
        return inputs, ct_fungible_inputs

    def get_relevant_outputs(self):
        outputs = Transaction.objects.filter(
            txid=self.txid,
            wallet__wallet_hash=self.wallet_hash
        ).exclude(
            token__tokenid=settings.WT_DEFAULT_CASHTOKEN_ID
        )
        ct_fungible_outputs = Transaction.objects.filter(
            txid=self.txid,
            address__wallet__wallet_hash=self.wallet_hash,
            cashtoken_ft__isnull=False
        )
        return outputs, ct_fungible_outputs

    def get_total_amount(self, qs, is_bch=True):
        if is_bch:
            value_sum = qs.aggregate(Sum('value'))['value__sum']
            # round down to zero if value sum is equal to or lesser than dust
            if value_sum <= 546:
                return 0
            return value_sum / (10 ** 8)
        return qs.aggregate(Sum('amount'))['amount__sum']

    def get_record_type(self, diff):
        if diff == 0:
            return ''
        elif diff < 0:
            return 'outgoing'
        else:
            return 'incoming'

    def get_change_address(self, inputs, outputs):
        change_address = None
        input_wallets = [x.address.wallet for x in inputs if x.address.wallet]
        input_addresses = [x.address for x in inputs if x.address.wallet]

        for tx_output in outputs:
            if tx_output.address.wallet:
                if tx_output.address.wallet in input_wallets:
                    change_address = tx_output.address.address
                    break
            else:
                if tx_output.address in input_addresses:
                    change_address = tx_output.address.address
                    break

        return change_address

    def get_txn_diff(self, total_outputs, total_inputs):
        diff = total_outputs - total_inputs
        return round(diff, 8)

    def parse(self):
        total_outputs = 0
        total_ct_outputs = 0
        total_inputs = 0
        total_ct_inputs = 0

        outputs, ct_outputs = self.get_relevant_outputs()
        inputs, ct_inputs = self.get_relevant_inputs()
        
        if outputs.exists():
            total_outputs = self.get_total_amount(outputs)
        if ct_outputs.exists():
            total_ct_outputs = self.get_total_amount(ct_outputs, is_bch=False)

        if inputs.exists():
            total_inputs = self.get_total_amount(inputs)
        if ct_inputs.exists():
            total_ct_inputs = self.get_total_amount(ct_inputs, is_bch=False)

        diff = self.get_txn_diff(total_outputs, total_inputs)
        diff_ct = self.get_txn_diff(total_ct_outputs, total_ct_inputs)

        return {
            'bch_or_slp': {
                'record_type': self.get_record_type(diff),
                'change_address': self.get_change_address(inputs, outputs),
                'diff': diff
            },
            'ct': {
                'record_type': self.get_record_type(diff_ct),
                'change_address': self.get_change_address(ct_inputs, ct_outputs),
                'diff': diff_ct
            }
        }
