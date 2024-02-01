import rampp2p.models as models
from django.db.models import Q
from django.conf import settings
from django.utils import timezone

from decimal import Decimal
from datetime import datetime

import logging
logger = logging.getLogger(__name__)

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

def is_appealable(id: int):
    appealable_at = models.Order.objects.get(pk=id).appealable_at    
    time_now = timezone.make_aware(datetime.now())
    return time_now >= appealable_at, appealable_at

def get_order_members_addresses(contract_id: int):
    arbiter, seller, buyer = get_order_members(contract_id)
    return {
        'arbiter': arbiter.address,
        'buyer': buyer.address,
        'seller': seller.address,
        'servicer': settings.SERVICER_ADDR
    }

def get_order_members(contract_id: int):
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

def get_trading_fees():
    # Retrieve fee values. Format must be in satoshi
    hardcoded_fee = Decimal(settings.HARDCODED_FEE).quantize(Decimal('0.00000000'))#/100000000
    arbitration_fee = Decimal(settings.ARBITRATION_FEE).quantize(Decimal('0.00000000'))#/100000000
    service_fee = Decimal(settings.SERVICE_FEE).quantize(Decimal('0.00000000'))#/100000000

    total_fee = hardcoded_fee + arbitration_fee + service_fee
    fees = {
        'hardcoded_fee': hardcoded_fee,
        'arbitration_fee': arbitration_fee,
        'service_fee': service_fee
    }
    return total_fee, fees

def get_latest_status(order_id: int):
    latest_status = models.Status.objects.filter(order__pk=order_id)
    if latest_status.exists():
        return latest_status.last()
    return None