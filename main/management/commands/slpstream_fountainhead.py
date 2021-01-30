from django.core.management.base import BaseCommand
from main.models import Token, Transaction
from main.tasks import save_record
from django.conf import settings
import logging
import requests
import json

LOGGER = logging.getLogger(__name__)


def run():
    url = "https://slpstream.fountainhead.cash/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjoge30KICB9Cn0="
    resp = requests.get(url, stream=True)
    source = 'slpstreamfountainhead'
    msg = 'Service not available!'
    LOGGER.info('socket ready in : %s' % source)
    for content in resp.iter_content(chunk_size=1024*1024):
        decoded_text = content.decode('utf8')
        if 'heartbeat' not in decoded_text:
            data = decoded_text.strip().split('data: ')[-1]
            proceed = True
            try:
                readable_dict = json.loads(data)
            except json.decoder.JSONDecodeError as exc:
                msg = f'Its alright. This is an expected error. --> {exc}'
                LOGGER.error(msg)
                proceed = False
            except Exception as exc:
                msg = f'This is a novel issue {exc}'
                LOGGER.error(msg)
                break
            if proceed:
                if len(readable_dict['data']) != 0:
                    try:
                        token_id = readable_dict['data'][0]['slp']['detail']['tokenIdHex']
                        token_query =  Token.objects.filter(tokenid=token_id)
                        if token_query.exists():
                            if 'tx' in readable_dict['data'][0].keys():
                                if readable_dict['data'][0]['slp']['valid']:
                                    txn_id = readable_dict['data'][0]['tx']['h']
                                    for trans in readable_dict['data'][0]['slp']['detail']['outputs']:
                                        slp_address = trans['address']
                                        amount = float(trans['amount']) / 100000000
                                        spent_index = trans['spentIndex']
                                        token_obj = token_query.first()
                                        tr_qs = Transaction.objects.filter(address=slp_address, txid=txn_id)
                                        args = (
                                            token_obj.tokenid,
                                            slp_address,
                                            txn_id,
                                            amount,
                                            source,
                                            None,
                                            spent_index
                                        )
                                        save_record(*args)
                    except (KeyError, UnicodeEncodeError):
                        pass
        LOGGER.error(msg)


class Command(BaseCommand):
    help = "Run the tracker of slpstream.fountainhead.cash"

    def handle(self, *args, **options):
        run()
