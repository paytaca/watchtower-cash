from django.db.models import Q
from django.conf import settings
from django.apps import apps

from datetime import datetime
from asgiref.sync import sync_to_async

import logging
logger = logging.getLogger(__name__)

def update_user_active_status(wallet_hash, is_online):
    Peer = apps.get_model('rampp2p', 'Peer')
    Arbiter = apps.get_model('rampp2p', 'Arbiter')
    try:
        user = Peer.objects.get(wallet_hash=wallet_hash)
        arbiter = Arbiter.objects.get(wallet_hash=wallet_hash)
        if arbiter and not arbiter.is_disabled:
            user = arbiter.first()

        user.is_online = is_online
        user.last_online_at = datetime.now()
        user.save()
    except (Peer.DoesNotExist, Arbiter.DoesNotExist) as err:
        logger.exception(err)

async def unread_orders_count(wallet_hash):
    Arbiter = apps.get_model('rampp2p', 'Arbiter')
    OrderMember = apps.get_model('rampp2p', 'OrderMember')
    Appeal = apps.get_model('rampp2p', 'Appeal')

    count = 0
    is_arbiter = await sync_to_async(Arbiter.objects.filter(wallet_hash=wallet_hash).exists)()

    if is_arbiter:
        # get arbiter orders
        member_orders_sync =  sync_to_async(OrderMember.objects.filter(Q(read_at__isnull=True) 
            & Q(arbiter__wallet_hash=wallet_hash)).values_list, thread_sensitive=True)
        member_orders = await member_orders_sync('order', flat=True)
        
        # count only the orders with appeals
        count_sync = sync_to_async(Appeal.objects.filter(order__in=member_orders).count, thread_sensitive=True)
        count = await count_sync()
    else:
        count_sync = sync_to_async(OrderMember.objects.filter(Q(read_at__isnull=True) 
            & Q(peer__wallet_hash=wallet_hash)).count, thread_sensitive=True)
        count = await count_sync()
    return count

def satoshi_to_bch(satoshi):
    return satoshi / settings.SATOSHI_PER_BCH

def bch_to_satoshi(bch):
    return bch * settings.SATOSHI_PER_BCH

def check_has_cashin_alerts(wallet_hash):
    Order = apps.get_model('rampp2p', 'Order')
    Status = apps.get_model('rampp2p', 'Status')

    queryset = Order.objects.filter(Q(is_cash_in=True) & Q(owner__wallet_hash=wallet_hash))
    queryset = queryset.order_by('-created_at')

    has_cashin_alerts = False
    for order in queryset:
        _is_seller = order.is_seller(wallet_hash)
        statuses = Status.objects.filter(order__id=order.id)
        if _is_seller:
            has_cashin_alerts = statuses.filter(seller_read_at__isnull=True).exists()
        else:
            has_cashin_alerts = statuses.filter(buyer_read_at__isnull=True).exists()
        if has_cashin_alerts:
            break
    return has_cashin_alerts