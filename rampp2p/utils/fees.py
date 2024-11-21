from django.conf import settings
from django.apps import apps
from decimal import Decimal

TradeFee = apps.get_model('rampp2p', 'TradeFee')

def get_trading_fees(trade_amount=None):
    ''' Retrieves the contract fees, format is in satoshi '''
    
    contract_fee = int(settings.CONTRACT_FEE)
    trade_amount = Decimal(trade_amount) if trade_amount else None
    service_fee = _get_service_fee(trade_amount=trade_amount)
    arbitration_fee = _get_arbitration_fee(trade_amount=trade_amount)

    total_fee = contract_fee + arbitration_fee + service_fee
    fees = {
        'contract_fee': int(contract_fee),
        'arbitration_fee': int(arbitration_fee),
        'service_fee': int(service_fee)
    }
    return total_fee, fees

def _get_service_fee(trade_amount=None):
    return _get_fee(trade_amount=trade_amount, category=TradeFee.FeeCategory.SERVICE)

def _get_arbitration_fee(trade_amount=None):
    return _get_fee(trade_amount=trade_amount, category=TradeFee.FeeCategory.ARBITRATION)

def _get_fee(trade_amount=None, category=None):
    fee = TradeFee.objects.filter(category=category).first()
    if fee:
       fee = fee.get_fee_value(trade_amount=trade_amount)
    else:
        if category == TradeFee.FeeCategory.SERVICE:
            fee = settings.SERVICE_FEE
        if category == TradeFee.FeeCategory.ARBITRATION:
            fee = settings.ARBITRATION_FEE
    return int(fee)