from django_filters import rest_framework as filters

from .models import (
    LongAccount,
    HedgePosition,
    HedgePositionOffer,
)


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
