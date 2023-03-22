from main.models import Transaction
from django.db.models import Sum


class HistoryParser(object):

    def __init__(self, txid, wallet_hash):
        self.txid = txid
        self.wallet_hash = wallet_hash

    def get_relevant_inputs(self):
        inputs = Transaction.objects.filter(
            spending_txid=self.txid,
            wallet__wallet_hash=self.wallet_hash
        ).exclude(
            token__is_cashtoken=True
        )
        ct_inputs = Transaction.objects.filter(
            spending_txid=self.txid,
            wallet__wallet_hash=self.wallet_hash,
            token__is_cashtoken=True
        )
        return inputs, ct_inputs

    def get_relevant_outputs(self):
        outputs = Transaction.objects.filter(
            txid=self.txid,
            wallet__wallet_hash=self.wallet_hash
        ).exclude(
            token__is_cashtoken=True
        )
        ct_outputs = Transaction.objects.filter(
            txid=self.txid,
            wallet__wallet_hash=self.wallet_hash,
            token__is_cashtoken=True
        )
        return outputs, ct_outputs

    def get_total_amount(self, qs):
        return qs.aggregate(Sum('amount'))['amount__sum']

    def get_record_type(self, diff):
        return 'incoming' if diff > 0 else 'outgoing'

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
            total_ct_outputs = self.get_total_amount(ct_outputs)

        if inputs.exists():
            total_inputs = self.get_total_amount(inputs)
        if ct_inputs.exists():
            total_ct_inputs = self.get_total_amount(ct_inputs)

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
