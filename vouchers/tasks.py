from celery import shared_task
from bitcash.keygen import public_key_to_address
from django.utils import timezone
from django.conf import settings
from django.db.models import (
    ExpressionWrapper,
    F,
    DateTimeField,
)

from main.utils.queries.node import Node
from vouchers.models import Voucher

import requests


@shared_task(queue='vouchers')
def refund_expired_vouchers():
    unclaimed_vouchers = Voucher.objects.filter(
        claimed=False,
        expired=False
    ).annotate(
        expiration_date=ExpressionWrapper(
            F('date_created') + timezone.timedelta(days=F('duration_days')),
            output_field=DateTimeField()
        )
    ).filter(
        expiration_date__lte=timezone.now()
    )    
    
    unclaimed_vouchers.update(expired=True)

    node = Node()
    block_chain_info = node.BCH.get_block_chain_info()
    median_time = block_chain_info['mediantime']

    for voucher in unclaimed_vouchers:
        pubkey = voucher.vault.pubkey
        address = bytearray.fromhex(pubkey)
        address = public_key_to_address(address)
        payload = {
            'params': {
                'category': voucher.category,
                'latestBlockTimestamp': median_time,
                'merchant': {
                    'address': address,
                    'pubkey': pubkey,
                },
            },
            'options': {
                'network': 'mainnet'
            }
        }
        response = requests.post(f'{settings.VOUCHER_EXPRESS_URL}/refund', json=payload)
        response = response.json()
