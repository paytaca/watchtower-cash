# Generated by Django 3.0.14 on 2024-04-30 08:34

from django.db import migrations
from django.db.models import Count, OuterRef, Subquery
from rampp2p.models import StatusType, TradeType
from django.utils import timezone

import logging
logger = logging.getLogger(__name__)

def init_completed_order_members(apps, schema_editor):
    Order = apps.get_model('rampp2p', 'Order')
    Status = apps.get_model('rampp2p', 'Status')
    OrderMember = apps.get_model('rampp2p', 'OrderMember')

    last_status = Status.objects.filter(
        order=OuterRef('pk'),
        status__in=[StatusType.CANCELED, StatusType.REFUNDED, StatusType.RELEASED]
    ).order_by('-created_at').values('order')[:1]

    orders = Order.objects.filter(pk__in=Subquery(last_status)).annotate(member_count=Count('members')).filter(member_count=0)
    for order in orders:
        logger.warn(f'Updating order #{order.id}')
        ad_snapshot = order.ad_snapshot
        # create order members
        seller, buyer = None, None
        if ad_snapshot.trade_type == TradeType.SELL:
            seller = ad_snapshot.ad.owner
            buyer = order.owner
        else:
            seller = order.owner
            buyer = ad_snapshot.ad.owner
        
        _ = OrderMember.objects.create(order=order, peer=seller, type='SELLER', read_at=timezone.now())
        _ = OrderMember.objects.create(order=order, peer=buyer, type='BUYER', read_at=timezone.now())

        # add arbiter as order member
        if order.arbiter:
            _, _ = OrderMember.objects.get_or_create(order=order, type='ARBITER', arbiter=order.arbiter)

class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0146_init_order_members_20240430_0653'),
    ]

    operations = [
        migrations.RunPython(init_completed_order_members)
    ]
