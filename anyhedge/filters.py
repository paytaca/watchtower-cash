import pytz
from datetime import datetime
from django.db import models
from django_filters import rest_framework as filters

from .models import (
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




class HedgePositionFilter(filters.FilterSet):
    FUNDING_STATUS_PENDING = 'pending'
    FUNDING_STATUS_PARTIAL = 'partial'
    FUNDING_STATUS_READY = 'ready'
    FUNDING_STATUS_COMPLETE = 'complete'
    FUNDING_STATUSES = [
        (FUNDING_STATUS_PENDING, FUNDING_STATUS_PENDING),
        (FUNDING_STATUS_PARTIAL, FUNDING_STATUS_PARTIAL),
        (FUNDING_STATUS_READY, FUNDING_STATUS_READY),
        (FUNDING_STATUS_COMPLETE, FUNDING_STATUS_COMPLETE),
    ]

    settled = filters.BooleanFilter(
        field_name='settlement', lookup_expr='isnull', exclude=True,
        help_text="Boolean filter for settlement state",
    )
    funding = filters.ChoiceFilter(
        method='filter_funding_status', choices=FUNDING_STATUSES,
        required=False,
        help_text=" | ".join([e[0] for e in FUNDING_STATUSES]),
    )

    class Meta:
        model = HedgePosition
        fields = [
            "hedge_wallet_hash",
            "long_wallet_hash",
            "settled",
            "funding",
        ]

    def filter_funding_status(self, queryset, name, value):
        if value == self.FUNDING_STATUS_PENDING:
            queryset = queryset.filter(hedge_funding_proposal__isnull=True, long_funding_proposal__isnull=True, funding_tx_hash__isnull=True)
        elif value == self.FUNDING_STATUS_PARTIAL:
            queryset = queryset.filter(
                models.Q(hedge_funding_proposal__isnull=False) | models.Q(long_funding_proposal__isnull=False),
                funding_tx_hash__isnull=True
            )
        elif value == self.FUNDING_STATUS_READY:
            queryset = queryset.filter(hedge_funding_proposal__isnull=False, long_funding_proposal__isnull=False, funding_tx_hash__isnull=True)
        elif value == self.FUNDING_STATUS_COMPLETE:
            queryset = queryset.filter(funding_tx_hash__isnull=False)
        return queryset


class HedgePositionOfferFilter(filters.FilterSet):
    statuses = filters.CharFilter(field_name="status", method="statuses_filter")
    exclude_wallet_hash = filters.CharFilter(field_name="wallet_hash", method="exclude_wallet_hash_filter")
    counter_party_wallet_hash = filters.CharFilter(field_name="counter_party_info__wallet_hash")

    class Meta:
        model = HedgePositionOffer
        fields= [
            "wallet_hash",
            "position",
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
