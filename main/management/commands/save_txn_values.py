from django.core.management.base import BaseCommand, CommandError
from django.db.models import F
from django.conf import settings

from main.models import Transaction
from main.tasks import process_cashtoken_tx
from main.utils.queries.bchn import BCHN

import datetime


class Command(BaseCommand):
    help = "Populate transactions' value fields"

    def handle(self, *args, **options):
        bch_txns = Transaction.objects.filter(
            token__name='bch'
        ).exclude(
            amount__gt=100000
        )
        bch_txns.update(value=(F('amount') * (10 ** 8)))

        self.stdout.write(self.style.SUCCESS(f'{bch_txns.count()} BCH transactions\' value field has been populated!'))
        
        cashtoken_txns = Transaction.objects.filter(token__tokenid=settings.WT_DEFAULT_CASHTOKEN_ID)
        bchn = BCHN()

        counter = 1
        total = cashtoken_txns.count()

        for txn in cashtoken_txns:
            self.stdout.write(f'Processing {counter} out of {total} cashtoken transactions...')

            if txn.cashtoken_ft:
                token = txn.cashtoken_ft
            else:
                token = txn.cashtoken_nft

            token_data = {
                'category': token.category,
                'amount': txn.amount
            }

            if txn.cashtoken_nft:
                token_data['nft'] = {
                    'capability': token.capability,
                    'commitment': token.commitment
                }

            raw_txn = bchn._get_raw_transaction(txn.txid)
            value = raw_txn['vout'][txn.index]['value']
            value *= (10 ** 8)

            process_cashtoken_tx(
                token_data,
                txn.address,
                txn.txid,
                block_id=txn.blockheight_id,
                index=txn.index,
                timestamp=datetime.datetime.timestamp(txn.tx_timestamp),
                value=value
            )
            counter += 1

        self.stdout.write(self.style.SUCCESS(f'{counter-1} CashToken transactions\' value field has been populated!'))
