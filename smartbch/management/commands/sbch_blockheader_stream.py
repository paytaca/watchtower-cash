import time
import logging
from django.core.management.base import BaseCommand

from smartbch.models import Block
from smartbch.utils.web3 import create_web3_client
from smartbch.utils.block import preload_block_range
from smartbch.tasks import parse_blocks_task

LOGGER = logging.getLogger(__name__)

def run(interval=3):
    w3 = create_web3_client()
    _filter = w3.eth.filter('latest')
    
    LOGGER.info("Streaming new smartbch blocks")
    max_block_in_db = Block.get_max_block_number()
    while True:
        try:
            entries = _filter.get_new_entries()
            new_block_numbers = []
            for entry in entries:
                block = w3.eth.get_block(entry)
                new_block_numbers.append(block.number)

            # determine start and end block to preload
            latest_block = max([max_block_in_db, *new_block_numbers])
            start_block = min([max_block_in_db, *new_block_numbers])

            # provide a hard cap to preload new blocks
            if latest_block - start_block >= 50:
                start_block = latest_block - 50

            if latest_block != start_block:
                preload_blocks_response = preload_block_range(start_block, latest_block)
                LOGGER.info(f"Preloaded new blocks: {preload_blocks_response[:2]}")
                max_block_in_db = latest_block

                LOGGER.info(f"Calling parse blocks task")
                parse_blocks_task.delay()

        except ValueError: 
            pass
        time.sleep(interval)



class Command(BaseCommand):
    help = "Stream and parse latest block/s in smartbch chain"

    def handle(self, *args, **options):
        run()
