import logging
import requests
import json
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
    qs = Shift.objects.filter(shift_status__in=['waiting', 'settling'])

    for shift in qs:
        shift_id = shift.shift_id
        url = 'https://sideshift.ai/api/v2/shifts/' + shift_id        

        fetched_shift = requests.get(url)        

        if fetched_shift.status_code == 200 or fetched_shift.status_code == 200:
            data = fetched_shift.json()
            
            shift.shift_status = data['status']

            if data['status'] == 'settled':
                shift.date_shift_completed = datetime.now()                
                shift.shift_info['txn_details'] = { 
                    'txid': data['settleHash']
                }

                logger.info(shift.shift_info)

            shift.save()



        