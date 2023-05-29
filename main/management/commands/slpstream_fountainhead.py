from django.core.management.base import BaseCommand
from django.db import transaction
from main.models import Token, Transaction, Subscription
from main.tasks import save_record, client_acknowledgement, send_telegram_message
from django.conf import settings
import logging
import requests
import json

LOGGER = logging.getLogger(__name__)


def run():
    url = "https://slpstream.fountainhead.cash/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjoge30KICB9Cn0="
    resp = requests.get(url, stream=True)
    source = 'slpstream_fountainhead'
    if resp.status_code != 200:
        msg = f"{source} is not available"
        LOGGER.error(msg)
        raise Exception(msg)
    LOGGER.info('socket ready in : %s' % source)
    data = ''  # data container
    for content in resp.iter_content(chunk_size=1024*1024):
        loaded_data = None
        if content:
            content = content.decode()
            if not content.startswith(':heartbeat'):
                if content.startswith('data:'):
                    if data:
                        # Data cointainer is ready for parsing
                        clean_data = data.lstrip('data: ').strip()
                        loaded_data = json.loads(clean_data, strict=False)
                    # Reset the data container
                    data = content
                else:
                    data += content
        if loaded_data is not None:
            if len(loaded_data['data']) > 0:
                info = loaded_data['data'][0]
                
                for _in in info['in']:
                    txid = _in['e']['h']
                    index = _in['e']['i']
                    
                if 'slp' in info.keys():
                    if info['slp']['valid']:
                        if 'detail' in info['slp'].keys():
                            slp_detail = info['slp']['detail']
                            if slp_detail['transactionType'] == 'GENESIS':
                                token_id = info['tx']['h']
                            else:
                                token_id = slp_detail['tokenIdHex']
                            index = 1
                            for output in slp_detail['outputs']:
                                slp_address = output['address']

                                subscription = Subscription.objects.filter(
                                    address__address=slp_address
                                )

                                # Disregard bch address that are not subscribed.
                                if subscription.exists():
                                    token, _ = Token.objects.get_or_create(tokenid=token_id)
                                    
                                    amount = float(output['amount'])
                                    # The amount given here is raw, it needs to be converted
                                    if token.decimals:
                                        amount = amount / (10 ** token.decimals)
                                    txn_id = info['tx']['h']
                                    txn_qs = Transaction.objects.filter(
                                        address__address=slp_address,
                                        txid=txn_id,
                                        index=index
                                    )
                                    if not txn_qs.exists():
                                        args = (
                                            token.tokenid,
                                            slp_address,
                                            txn_id,
                                            amount,
                                            source,
                                            None,
                                            index
                                        )
                                        obj_id, created = save_record(*args)
                                        if created:
                                            client_acknowledgement(obj_id)

                                    msg = f"{source}: {txn_id} | {slp_address} | {amount} | {token_id}"
                                    LOGGER.info(msg)
                                index += 1
                            
                            


class Command(BaseCommand):
    help = "Run the tracker of slpstream.fountainhead.cash"

    def handle(self, *args, **options):
        run()
