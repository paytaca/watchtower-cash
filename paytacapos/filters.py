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
    country = filters.CharFilter(field_name="location__country", lookup_expr="icontains")
    city = filters.CharFilter(field_name="location__city", lookup_expr="icontains")
    street = filters.CharFilter(field_name="location__street", lookup_expr="icontains")
    category = filters.CharFilter(field_name="category__name", lookup_expr="icontains")

    class Meta:
        model = Merchant
        fields = [
            "country",
            "city",
            "street",
            "category",
        ]
