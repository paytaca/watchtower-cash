from django.db.models import Q
from django.conf import settings
from django.apps import apps
from decimal import Decimal, ROUND_DOWN
from datetime import datetime
from asgiref.sync import sync_to_async
from packaging.version import Version

import logging
logger = logging.getLogger(__name__)

def update_user_active_status(wallet_hash, is_online):
    if wallet_hash == None: return
    
    Peer = apps.get_model('rampp2p', 'Peer')
    Arbiter = apps.get_model('rampp2p', 'Arbiter')
    try:
        user = Peer.objects.get(wallet_hash=wallet_hash)
        arbiter = Arbiter.objects.filter(wallet_hash=wallet_hash)
        if arbiter.exists() and not arbiter.first().is_disabled:
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
    return Decimal(satoshi / settings.SATOSHI_PER_BCH).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN) # truncate to 8 decimals

def bch_to_satoshi(bch):
    return int(Decimal(bch) * settings.SATOSHI_PER_BCH)

def bch_to_fiat(bch_amount, fiat_price):
    return Decimal(bch_amount) * Decimal(fiat_price)

def fiat_to_bch(fiat_amount, fiat_price):
    return Decimal(fiat_amount) / Decimal(fiat_price)

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

def version_in_range(version, platform='web'):
    version_to_check = Version(version)

    AppVersion = apps.get_model('rampp2p', 'AppVersion')
    current_version = AppVersion.objects.filter(platform=platform).last()
    if not current_version:
       return False, None
    
    lower_bound = Version(current_version.min_required_version)
    upper_bound = Version(current_version.latest_version)

    is_in_range = lower_bound <= version_to_check <= upper_bound
    logger.info(f"Is {version_to_check} within the range {lower_bound} and {upper_bound}? {is_in_range}")
    
    return is_in_range, lower_bound

def is_min_version_compatible(min_required_version, version):
    version_to_check = Version(version)
    lower_bound = Version(min_required_version)
    is_compatible = lower_bound <= version_to_check
    logger.info(f"Is {version_to_check} compatible with {lower_bound}? {is_compatible}")
    return is_compatible