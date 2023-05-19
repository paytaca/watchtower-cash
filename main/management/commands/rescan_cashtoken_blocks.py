from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from main.tasks import query_transaction, ready_to_accept
from main.utils.queries.node import Node

from celery import chord
import requests, logging, time


LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Rescan blocks to record missed transactions since first cashtoken block"

    def handle(self, *args, **options):
        NODE = Node()

        latest_block = NODE.BCH.get_latest_block()

        curr_block = 792773
        max_retries = 10
        key = 0

        if settings.BCH_NETWORK == 'chipnet':
            curr_block = 100000
            
        while curr_block < latest_block:
            subtasks = []
            LOGGER.info(f'Rescanning block {curr_block}')

            transactions = NODE.BCH.get_block(curr_block)

            for txid in transactions:
                retries = 0

                while retries < max_retries:
                    response = requests.post(f'{settings.PAYTACA_BCMR_URL}/webhook/', json={'tx_hash': txid})
                    if response.status_code == 200:
                        break
                        
                    retries += 1
                    time.sleep(1)
                
                subtasks.append(query_transaction.si(txid, key))

            if subtasks:
                callback = ready_to_accept.si(curr_block, len(subtasks))
                chord(subtasks)(callback)

            curr_block += 1
            key += 1

        self.stdout.write(self.style.SUCCESS('Rescanning block tasks queued!'))
