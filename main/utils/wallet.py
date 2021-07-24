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
        )
        return inputs

    def get_relevant_outpus(self):
        outputs = Transaction.objects.filter(
            txid=self.txid,
            wallet__wallet_hash=self.wallet_hash
        )
        return outputs

    def parse(self):
        total_outputs = 0
        outputs = self.get_relevant_outpus()
        if outputs.exists():
            outputs_agg = outputs.aggregate(Sum('amount'))
            total_outputs = outputs_agg['amount__sum']

        total_inputs = 0
        inputs = self.get_relevant_inputs()
        if inputs.exists():
            inputs_agg = inputs.aggregate(Sum('amount'))
            total_inputs = inputs_agg['amount__sum']

        diff = total_outputs - total_inputs
        diff = round(diff, 8)
        if diff > 0:
            record_type = 'incoming'
        else:
            record_type = 'outgoing'

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

        return record_type, diff, change_address
