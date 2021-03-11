
from django.core.management.base import BaseCommand
from django.db import transaction
from main.models import Token, Transaction
from main.tasks import save_record
from django.conf import settings
import logging
import traceback
import requests
import json

LOGGER = logging.getLogger(__name__)


def run():
    """
    A live stream of BCH transactions via bitsocket
    """
    source = 'bitsocket'
    url = "https://bitsocket.bch.sx/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjoge30KICB9Cn0="
    resp = requests.get(url, stream=True)

    if resp.status_code != 200:
        return f'{source.upper()} IS NOT AVAILABLE.'
        
    LOGGER.info(f"{source.upper()} WILL SERVE DATA SHORTLY...")
    previous = ''

    for content in resp.iter_content(chunk_size=1024*1024):
        loaded_data = None
        try:
            content = content.decode('utf8')
            if '"tx":{"h":"' in previous:
                data = previous + content
                data = data.strip().split('data: ')[-1]
                loaded_data = json.loads(data)

                proceed = True
        except (ValueError, UnicodeDecodeError, TypeError) as exc:
            continue
        except json.decoder.JSONDecodeError as exc:
            continue
        except Exception as exc:
            REDIS_STORAGE.set('BITSOCKET', 0)
            return f"UNEXPECTED ERROR FOUND IN {source.upper()}"
        previous = content
        if loaded_data is not None:
            if len(loaded_data['data']) != 0:
                txn_id = loaded_data['data'][0]['tx']['h']
                for out in loaded_data['data'][0]['out']: 
                    if 'e' in out.keys():
                        amount = out['e']['v'] / 100000000
                        spent_index = out['e']['i']
                        if amount and 'a' in out['e'].keys():
                            bchaddress = 'bitcoincash:' + str(out['e']['a'])
                            args = (
                                'bch',
                                bchaddress,
                                txn_id,
                                amount,
                                source,
                                None,
                                spent_index
                            )
                            if not Transaction.objects.filter(txid=txn_id).exists():
                                save_record(*args)
                            msg = f"{source}: {txn_id} | {bchaddress} | {amount} "
                            LOGGER.info(msg)

class Command(BaseCommand):
    help = "Run the tracker of bitsocket"

    def handle(self, *args, **options):
        run()
