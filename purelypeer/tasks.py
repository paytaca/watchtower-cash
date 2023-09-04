from celery import shared_task

from django.utils import timezone
from django.conf import settings
from django.db.models import (
    ExpressionWrapper,
    F,
    DateTimeField,
)

from purelypeer.models import Voucher
from purelypeer.websocket import send_websocket_data


@shared_task(queue='claim_expired_unclaimed_vouchers')
def claim_expired_unclaimed_vouchers():
    unclaimed_vouchers = Voucher.objects.filter(
        used=False,
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
        send_websocket_data(
            voucher.vault.merchant.receiving_address,
            None,
            {
                'lock_nft_category': voucher.key_category
            },
            room_name=settings.VOUCHER_ROOM
        )
