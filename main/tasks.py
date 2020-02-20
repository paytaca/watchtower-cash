from __future__ import absolute_import, unicode_literals
from celery import shared_task
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, queue='task_a')
def task_a(self):
    logger.info('execute task A ')

@shared_task(bind=True, queue='task_b')
def task_b(self):
    logger.info('execute task B ')

@shared_task(bind=True, queue='task_c')
def task_b(self):
    logger.info('execute task C ')