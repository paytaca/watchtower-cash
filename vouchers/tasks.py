from celery import shared_task

from django.utils import timezone
from django.conf import settings
from django.db.models import (
    ExpressionWrapper,
    F,
    DateTimeField,
)

from vouchers.models import Voucher
from vouchers.websocket import send_websocket_data
from vouchers.js.runner import ScriptFunctions


@shared_task(queue='claim_expired_unclaimed_vouchers')
def claim_expired_unclaimed_vouchers():
    unclaimed_vouchers = Voucher.objects.filter(
        claimed=False,
        expired=False
    ).annotate(
        expiration_date=ExpressionWrapper(
            F('date_created') + timedelta(days=F('duration_days')),
            output_field=DateTimeField()
        )
    ).filter(
        expiration_date__lte=timezone.now()
    )    
    
    unclaimed_vouchers.update(expired=True)

    for voucher in unclaimed_vouchers:
        merchant_receiving_address = ScriptFunctions.pubkeyToCashAddress(
            dict(pubkey=voucher.vault.merchant.receiving_pubkey)
        )
        
        send_websocket_data(
            merchant_receiving_address,
            None,
            {
                'category': voucher.category
            },
            room_name=settings.VOUCHER_ROOM
        )
