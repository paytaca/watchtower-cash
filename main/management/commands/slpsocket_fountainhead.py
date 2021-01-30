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
    url = "https://slpsocket.fountainhead.cash/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjogewogICAgfQogIH0KfQ=="
    resp = requests.get(url, stream=True)
    source = 'slpsocket.fountainhead.cash'
    LOGGER.info('socket ready in : %s' % source)
    previous = ''
    msg = 'Service not available!'
    for content in resp.iter_content(chunk_size=1024*1024):
        loaded_data = None
        try:
            content = content.decode('utf8')
            if '"tx":{"h":"' in previous:
                data = previous + content
                data = data.strip().split('data: ')[-1]
                loaded_data = json.loads(data)
        except (ValueError, UnicodeDecodeError, TypeError) as exc:
            msg = traceback.format_exc()
            msg = f'Its alright. This is an expected error. --> {msg}'
            LOGGER.error(msg)
        except json.decoder.JSONDecodeError as exc:
            msg = f'Its alright. This is an expected error. --> {exc}'
            LOGGER.error(msg)
        except Exception as exc:
            msg = f'Novel exception found --> {exc}'
            break
        previous = content
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
