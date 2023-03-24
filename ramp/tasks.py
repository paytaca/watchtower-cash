import logging
from datetime import datetime

from celery import shared_task
from .models import (
    Shift
)


logger = logging.getLogger(__name__)

@shared_task(bind=True, queue='ramp__shift_expiration')
def update_shift_status(self):

    logger.info('CHECKING FOR EXPIRED SHIFTS')
    # get waiting
    qs = Shift.objects.filter(shift_status='waiting')

    for shift in qs:
        date = shift.shift_info['shift_expiration']

        expiry_date = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%fZ")
        date_now = datetime.now()

        if expiry_date < date_now:

            shift.shift_status = 'expired'
            shift.save()


        