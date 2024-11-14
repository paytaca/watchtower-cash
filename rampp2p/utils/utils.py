import rampp2p.models as models
from django.db.models import Q
from django.conf import settings
from django.utils import timezone

from decimal import Decimal
from datetime import datetime
import hashlib
from asgiref.sync import sync_to_async

import logging
logger = logging.getLogger(__name__)

SATS_PER_BCH = 100000000

def update_user_active_status(wallet_hash, is_online):
    try:
        user = models.Peer.objects.get(wallet_hash=wallet_hash)
    except models.Peer.DoesNotExist:
        return
    
    arbiter = models.Arbiter.objects.filter(wallet_hash=wallet_hash)
    if arbiter.exists() and not arbiter.first().is_disabled:
        user = arbiter.first()

    user.is_online = is_online
    user.last_online_at = datetime.now()
    user.save()

async def unread_orders_count(wallet_hash):
    count = 0
    is_arbiter = await sync_to_async(models.Arbiter.objects.filter(wallet_hash=wallet_hash).exists)()

    if is_arbiter:
        # get arbiter orders
        member_orders_sync =  sync_to_async(models.OrderMember.objects.filter(Q(read_at__isnull=True) 
            & Q(arbiter__wallet_hash=wallet_hash)).values_list, thread_sensitive=True)
        member_orders = await member_orders_sync('order', flat=True)
        # count only the orders with appeals
        count_sync = sync_to_async(models.Appeal.objects.filter(order__in=member_orders).count, thread_sensitive=True)
        count = await count_sync()
    else:
        count_sync = sync_to_async(models.OrderMember.objects.filter(Q(read_at__isnull=True) 
            & Q(peer__wallet_hash=wallet_hash)).count, thread_sensitive=True)
        count = await count_sync()
    return count

def generate_chat_session_ref(input_string):
    # Encode the string to bytes
    encoded_string = input_string.encode('utf-8')
    # Create an SHA-256 hash object
    sha256_hash = hashlib.sha256(encoded_string)
    # Get the hexadecimal representation of the hash
    hashed_string = sha256_hash.hexdigest()
    return hashed_string

def is_seller(order: models.Order, wallet_hash: str):
    seller = order.owner
    if order.ad_snapshot.trade_type == models.TradeType.SELL:
        seller = order.ad_snapshot.ad.owner
    if wallet_hash == seller.wallet_hash:
        return True
    return False

def is_buyer(order: models.Order, wallet_hash: str):
    buyer = order.owner
    if order.ad_snapshot.trade_type == models.TradeType.BUY:
        buyer = order.ad_snapshot.ad.owner
    if wallet_hash == buyer.wallet_hash:
        return True
    return False

def is_arbiter(order: models.Order, wallet_hash: str):
    return wallet_hash == order.arbiter.wallet_hash

def is_appealable(id: int):
    appealable_at = models.Order.objects.get(pk=id).appealable_at    
    time_now = timezone.make_aware(datetime.now())
    return time_now >= appealable_at, appealable_at

def get_order_members_addresses(contract_id: int):
    arbiter, seller, buyer = get_contract_members(contract_id)
    return {
        'arbiter': arbiter.address,
        'buyer': buyer.address,
        'seller': seller.address,
        'servicer': settings.SERVICER_ADDR
    }

def get_contract_members(contract_id: int):
    members = models.ContractMember.objects.filter(contract__id=contract_id)
    arbiter, seller, buyer = None, None, None
    for member in members:
        type = member.member_type
        if (type == models.ContractMember.MemberType.ARBITER):
            arbiter = member
        if (type == models.ContractMember.MemberType.SELLER):
            seller = member
        if (type == models.ContractMember.MemberType.BUYER):
            buyer = member

    return arbiter, seller, buyer

def get_order_members(order_id: int):
    members = models.OrderMember.objects.filter(order__id=order_id)
    arbiter, seller, buyer = None, None, None
    for member in members:
        type = member.type
        if (type == models.OrderMember.MemberType.ARBITER):
            arbiter = member
        if (type == models.OrderMember.MemberType.SELLER):
            seller = member
        if (type == models.OrderMember.MemberType.BUYER):
            buyer = member

    return {
        'arbiter': arbiter,
        'seller': seller,
        'buyer': buyer
    }

def sats_to_bch(sats):
    return sats / SATS_PER_BCH

def bch_to_sats(bch):
    return bch * SATS_PER_BCH

def get_service_fee(trade_amount=None):
    service_fee = models.ServiceFee.objects.first()
    if service_fee:
       service_fee = service_fee.get_fee_value(trade_amount=trade_amount)
    else:
       service_fee = settings.SERVICE_FEE
    return int(service_fee)

def get_trading_fees(trade_amount=None):
    # Retrieve fee values. Format must be in satoshi
    hardcoded_fee = Decimal(settings.HARDCODED_FEE).quantize(Decimal('0.00000000'))#/100000000
    arbitration_fee = Decimal(settings.ARBITRATION_FEE).quantize(Decimal('0.00000000'))#/100000000
    trade_amount = Decimal(trade_amount) if trade_amount else None
    service_fee = get_service_fee(trade_amount=trade_amount)

    total_fee = hardcoded_fee + arbitration_fee + service_fee
    fees = {
        'hardcoded_fee': int(hardcoded_fee),
        'arbitration_fee': int(arbitration_fee),
        'service_fee': int(service_fee)
    }
    return total_fee, fees

def get_last_status(order_id: int):
    latest_status = models.Status.objects.filter(order__pk=order_id)
    if latest_status.exists():
        return latest_status.last()
    return None

def check_has_cashin_alerts(wallet_hash):
    queryset = models.Order.objects.filter(Q(is_cash_in=True) & Q(owner__wallet_hash=wallet_hash))
    queryset = queryset.order_by('-created_at')

    has_cashin_alerts = False
    for order in queryset:
        _is_seller = is_seller(order, wallet_hash)
        statuses = models.Status.objects.filter(order__id=order.id)
        if _is_seller:
            has_cashin_alerts = statuses.filter(seller_read_at__isnull=True).exists()
        else:
            has_cashin_alerts = statuses.filter(buyer_read_at__isnull=True).exists()
        if has_cashin_alerts:
            break
    return has_cashin_alerts