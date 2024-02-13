from django_filters import rest_framework as filters

from .models import (
    PosDevice,
    Branch,
    Merchant,
)

class PosDevicetFilter(filters.FilterSet):
    class Meta:
        model = PosDevice
        fields= [
            "wallet_hash",
        ]


class BranchFilter(filters.FilterSet):
    wallet_hash = filters.CharFilter(field_name="merchant__wallet_hash")

    class Meta:
        model = Branch
        fields = [
            "wallet_hash",
        ]


class MerchantFilter(filters.FilterSet):
    class Meta:
        model = Merchant
        fields = (
            'location__country',
            'location__latitude',
            'location__longitude',
        )
