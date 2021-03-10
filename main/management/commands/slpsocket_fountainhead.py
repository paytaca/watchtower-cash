from django.core.management.base import BaseCommand
from main.models import Token, Transaction
from main.tasks import save_record
from django.conf import settings
import logging
import traceback
import requests
import json

LOGGER = logging.getLogger(__name__)


def run():
    url = "https://slpsocket.fountainhead.cash/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjoge30KICB9Cn0="
    resp = requests.get(url, stream=True)
    source = 'slpsocket_fountainhead'
    LOGGER.info('socket ready in : %s' % source)
    data = ''
    msg = 'Service not available!'
    for content in resp.iter_content(chunk_size=1024*1024):
        loaded_data = None
        if content:
            content = content.decode()
            if not content.startswith(':heartbeat'):
                if content.startswith('data:'):
                    data = content
                else:
                    data += content
                if data.startswith('data:') and data.endswith('\n\n'):
                    clean_data = data.lstrip('data: ').strip()
                    loaded_data = json.loads(clean_data, strict=False)
        if loaded_data is not None:
            if len(loaded_data['data']) > 0:
                info = loaded_data['data'][0]
                if 'slp' in info.keys():
                    if info['slp']['valid']:
                        if 'detail' in info['slp'].keys():
                            if 'tokenIdHex' in info['slp']['detail'].keys():
                                token_id = info['slp']['detail']['tokenIdHex']
                                token_query =  Token.objects.filter(tokenid=token_id)
                                if token_query.exists():
                                    spent_index = 1
                                    for trans in info['slp']['detail']['outputs']:
                                        amount = float(trans['amount'])
                                        slp_address = trans['address']
                                        if 'tx' in info.keys():
                                            txn_id = info['tx']['h']
                                            token_obj = token_query.first()
                                            args = (
                                                token_id,
                                                slp_address,
                                                txn_id,
                                                amount,
                                                source,
                                                None,
                                                spent_index
                                            )
                                            save_record(*args)
                                            msg = f"{source}: {txn_id} | {slp_address} | {amount} | {token_id}"
                                            LOGGER.info(msg)
                                        spent_index += 1
    LOGGER.error(msg)


class Command(BaseCommand):
    help = "Run the tracker of slpsocket.fountainhead.cash"

    def handle(self, *args, **options):
        run()
