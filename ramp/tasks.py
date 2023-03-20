import logging

from celery import shared_task

logger = logging.getLogger(__name__)

@shared_task(bind=True, queue='ramp__shift_expiration')
def update_shift_status():
    logger.info('Testing testing')
