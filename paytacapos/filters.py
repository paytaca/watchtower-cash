from django_filters import rest_framework as filters

from .models import *
from django.db.models import Q


class PosDeviceFilter(filters.FilterSet):
    class Meta:
        model = PosDevice
        fields = [
            "merchant_id",
            "branch_id",
            "wallet_hash",
        ]


class BranchFilter(filters.FilterSet):
    wallet_hash = filters.CharFilter(field_name="merchant__wallet_hash")

    class Meta:
        model = Branch
        fields = [
            "merchant_id",
            "wallet_hash",
        ]


class MerchantFilter(filters.FilterSet):
    wallet_hashes = filters.CharFilter(method="wallet_hashes_filter")
    country = filters.CharFilter(field_name="location__country", lookup_expr="icontains")
    city = filters.CharFilter(field_name="location__city", lookup_expr="icontains")
    street = filters.CharFilter(field_name="location__street", lookup_expr="icontains")
    category = filters.CharFilter(field_name="category__name", lookup_expr="icontains")
    has_vault = filters.BooleanFilter(method="has_vault_filter")

    active = filters.BooleanFilter()
    verified = filters.BooleanFilter()
    name = filters.CharFilter(method="name_address_filter")

    ordering = filters.OrderingFilter(
        fields=(
            ('id', 'id'),
            ('slug', 'slug'),
            ('name', 'name'),
            ('category__name', 'category'),
            ('active', 'active'),
            ('last_update', 'last_update'),
        ),
    )

    class Meta:
        model = Merchant
        fields = [
            "country",
            "city",
            "street",
            "category",
        ]

    def wallet_hashes_filter(self, queryset, name, value):
        if not isinstance(value, str):
            return queryset

        wallet_hashes = [wallet_hash.strip() for wallet_hash in value.split(",") if wallet_hash.strip()]
        return queryset.filter(wallet_hash__in=wallet_hashes)

    def name_address_filter(self, queryset, name, value):
        return queryset.filter( 
            Q(name__icontains=value) | 
            Q(category__name__icontains=value) | 
            Q(location__location__icontains=value) | 
            Q(location__city__icontains=value) | 
            Q(location__street__icontains=value) | 
            Q(location__country__icontains=value) | 
            Q(location__town__icontains=value) | 
            Q(location__province__icontains=value) | 
            Q(location__state__icontains=value) 
        )

    def has_vault_filter(self, queryset, name, value):
        return queryset.exclude(pubkey__isnull=value)