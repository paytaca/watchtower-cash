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

    def get_total_ct_amount(self, qs):
        _qs = qs.order_by() # GROUP BY doesnt work as expected sometimes if there is ordering
        result = _qs.values("cashtoken_ft_id") \
                .annotate(total=Sum("amount")) \
                .values("cashtoken_ft_id", "total")

        result_map = { data["cashtoken_ft_id"]: data["total"] for data in result }
        return result_map

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

    def parse_ct(self, ct_inputs, ct_outputs):
        change_address = self.get_change_address(ct_inputs, ct_outputs)
        total_ct_inputs_map = {} # { <category>: <total> }
        total_ct_outputs_map = {} # { <category>: <total> }

        if ct_inputs.exists():
            total_ct_inputs_map = self.get_total_ct_amount(ct_inputs)

        if ct_outputs.exists():
            total_ct_outputs_map = self.get_total_ct_amount(ct_outputs)

        categories = { *total_ct_inputs_map.keys(), *total_ct_outputs_map.keys() }

        results = {}
        for category in categories:
            total_inputs = total_ct_inputs_map.get(category, 0)
            total_outputs = total_ct_outputs_map.get(category, 0)

            diff = self.get_txn_diff(total_outputs, total_inputs)
            record_type = self.get_record_type(diff)
            results[f"ct/{category}"] = dict(
                record_type=record_type,
                change_address=change_address,
                diff=diff,
            )

        return results

    def parse(self):
        total_outputs = 0
        total_inputs = 0

        outputs, ct_outputs = self.get_relevant_outputs()
        inputs, ct_inputs = self.get_relevant_inputs()

        if outputs.exists():
            total_outputs = self.get_total_amount(outputs)

        if inputs.exists():
            total_inputs = self.get_total_amount(inputs)

        diff = self.get_txn_diff(total_outputs, total_inputs)

        result = {
            'bch_or_slp': {
                'record_type': self.get_record_type(diff),
                'change_address': self.get_change_address(inputs, outputs),
                'diff': diff
            },
            **self.parse_ct(ct_inputs, ct_outputs),
        }

        return result
