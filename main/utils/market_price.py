import json
import requests
from decimal import Decimal
from datetime import timedelta 
from django.db import models
from django.apps import apps
from main.models import AssetPriceLog

from anyhedge.utils.price_oracle import (get_price_messages, save_price_oracle_message)


def fetch_currency_value_for_timestamp(timestamp, currency="USD"):
    """
    Get currency price with closest timestamp within a +/- 30 seconds margin

    Parameters
        timestamp: datetime.datetime

    Returns:
        (price_value: decimal.Decimal, actual_timestamp: datetime.datetime, source: str): tuple
            - price_value: (e.g. USD/BCH)
            - actual_timestamp: the actual timestamp returned from the source
            - source: where the data came from
    """
    timestamp_range_low = timestamp - timedelta(seconds=30)
    timestamp_range_high = timestamp + timedelta(seconds=30)
    closest = AssetPriceLog.objects.filter(
        currency=currency,
        timestamp__gt = timestamp_range_low,
        timestamp__lt = timestamp_range_high,
    ).annotate(
        diff=models.Func(models.F("timestamp"), timestamp, function="GREATEST") - models.Func(models.F("timestamp"), timestamp, function="LEAST")
    ).order_by("diff").first()

    if closest:
        return (closest.price_value, closest.timestamp, closest.source)

    try:
        Oracle = apps.get_model("anyhedge", "Oracle")
        PriceOracleMessage = apps.get_model("anyhedge", "PriceOracleMessage")

        oracles = Oracle.objects.filter(asset_currency=currency)
        oracles_decimals_map = { oracle.pubkey: oracle.asset_decimals for oracle in oracles }
        closest = PriceOracleMessage.objects.filter(
            pubkey__in=oracles_decimals_map.keys(),
            message_timestamp__gt = timestamp_range_low,
            message_timestamp__lt = timestamp_range_high,
        ).annotate(
            diff=models.Func(models.F("message_timestamp"), timestamp, function="GREATEST") - models.Func(models.F("message_timestamp"), timestamp, function="LEAST")
        ).order_by("diff").first()

        if closest:
            asset_decimals = oracles_decimals_map[closest.pubkey]
            price_value = Decimal(closest.price_value) / 10 ** asset_decimals
            return (price_value, closest.message_timestamp, f"anyhedge:{closest.pubkey}")
    except LookupError:
        pass

    try:
        Oracle = apps.get_model("anyhedge", "Oracle")
        oracles = Oracle.objects.filter(asset_currency=currency)
        for oracle in oracles:
            price_messages = get_price_messages(
                oracle_pubkey=oracle.pubkey,
                relay=oracle.relay or None,
                port=oracle.port or None,
                min_message_timestamp=int(timestamp_range_low.timestamp()),
                max_message_timestamp=int(timestamp_range_high.timestamp()),
            )
            closest = None
            for price_msg in price_messages:
                price_msg_obj = save_price_oracle_message(oracle.pubkey, price_msg)
                obj_diff = abs(price_msg_obj.message_timestamp - timestamp)
                if closest is not None:
                    closest_diff = abs(closest.message_timestamp - timestamp)
                    if obj_diff < closest_diff:
                        closest = price_msg_obj
                elif obj_diff < timedelta(seconds=30):
                    closest = price_msg_obj

            if closest:
                asset_decimals = oracle.asset_decimals
                price_value = Decimal(closest.price_value) / 10 ** asset_decimals
                return (price_value, closest.message_timestamp, f"anyhedge-oracle:{closest.pubkey}")
    except LookupError:
        pass

    return None
