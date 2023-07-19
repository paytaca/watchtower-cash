from celery import shared_task
from paytacagifts.models import Gift
from main.models import Transaction
from django.utils import timezone


@shared_task(queue='monitor-gifts')
def check_unfunded_gifts():
    unfunded_gifts = Gift.objects.filter(date_funded__isnull=True)
    for gift in unfunded_gifts:
        funding_check = Transaction.objects.filter(address__address=gift.address)
        if funding_check.exists():
            funding_tx = funding_check.first()
            gift.date_funded = funding_tx.date_created
            gift.save()


@shared_task(queue='monitor-gifts')
def check_unclaimed_gifts():
    funded_gifts = Gift.objects.filter(date_funded__isnull=False)
    for gift in funded_gifts:
        funding_tx = Transaction.objects.filter(
            address__address=gift.address
        ).first()
        if funding_tx:
            if funding_tx.spent:
                gift.date_claimed = timezone.now()
                gift.save()
