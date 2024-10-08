# Generated by Django 3.0.14 on 2024-09-25 05:53

from django.db import migrations
from django.utils import timezone

import logging
logger = logging.getLogger(__name__)

def read_order_statuses(apps, schema_editor):
    '''Mark as read by seller & buyer all existing order statuses'''
    Status = apps.get_model('rampp2p', 'Status')

    statuses = Status.objects.all()
    for status in statuses:
        status.seller_read_at = timezone.now()
        status.buyer_read_at = timezone.now()
        status.save()
    logger.warning(f'Marked read {statuses.count()} order statuses')

class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0189_auto_20240923_0645'),
    ]

    operations = [
        migrations.RunPython(read_order_statuses)
    ]
