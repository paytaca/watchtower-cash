import pytz
from datetime import datetime
from django_filters import rest_framework as filters

from .models import (
    LongAccount,
    HedgePosition,
    HedgePositionOffer,

    Oracle,
    PriceOracleMessage,
)

class TimestampFilter(filters.NumberFilter):
    def filter(self, qs, value, *args, **kwargs):
        if value is not None:
            value = datetime.fromtimestamp(value).replace(tzinfo=pytz.UTC)

        return super().filter(qs, value, *args, **kwargs)


class LongAccountFilter(filters.FilterSet):

    class Meta:
        model = LongAccount
        fields= [
            "wallet_hash",
        ]


class HedgePositionFilter(filters.FilterSet):
    class Meta:
        model = HedgePosition
        fields = [
            "hedge_wallet_hash",
            "long_wallet_hash"
        ]


class HedgePositionOfferFilter(filters.FilterSet):
    statuses = filters.CharFilter(field_name="status", method="statuses_filter")
    exclude_wallet_hash = filters.CharFilter(field_name="wallet_hash", method="exclude_wallet_hash_filter")

    class Meta:
        model = HedgePositionOffer
        fields= [
            "wallet_hash",
        ]
    
    def statuses_filter(self, queryset, name, value):
        return queryset.filter(status__in=str(value).split(","))
    
    def exclude_wallet_hash_filter(self, queryset, name, value):
        return queryset.exclude(wallet_hash=value)

class OracleFilter(filters.FilterSet):
    class Meta:
        model = Oracle
        fields = {
            'asset_name': ['iexact', 'icontains'],
        }


class PriceOracleMessageFilter(filters.FilterSet):
    pubkey = filters.CharFilter(field_name="pubkey")
    timestamp_after = TimestampFilter(field_name="message_timestamp", lookup_expr="gt")
    timestamp_before = TimestampFilter(field_name="message_timestamp", lookup_expr="lt")
    price_sequence_after = filters.NumberFilter(field_name="price_sequence", lookup_expr="gt")
    price_sequence_before = filters.NumberFilter(field_name="price_sequence", lookup_expr="lt")
    message_sequence_after = filters.NumberFilter(field_name="message_sequence", lookup_expr="gt")
    message_sequence_before = filters.NumberFilter(field_name="message_sequence", lookup_expr="lt")

    class Meta:
        model = PriceOracleMessage
        fields = [
            "pubkey",
            "price_sequence",
            "message_sequence",
            "timestamp_after",
            "timestamp_before",
            "price_sequence_after",
            "price_sequence_before",
            "message_sequence_after",
            "message_sequence_before",
        ]
