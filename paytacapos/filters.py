from django_filters import rest_framework as filters

from .models import *


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
    device_vault_token_address = filters.CharFilter(method="vault_address_filter")
    # no_vault = filters.BooleanFilter(field_name="vault", lookup_expr="isnull")

    active = filters.BooleanFilter()
    verified = filters.BooleanFilter()
    name = filters.CharFilter(lookup_expr="icontains")

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
            "device_vault_token_address",
            # "no_vault",
        ]

    def wallet_hashes_filter(self, queryset, name, value):
        if not isinstance(value, str):
            return queryset

        wallet_hashes = [wallet_hash.strip() for wallet_hash in value.split(",") if wallet_hash.strip()]
        return queryset.filter(wallet_hash__in=wallet_hashes)

    def vault_address_filter(self, queryset, name, value):
        pos_devices = PosDevice.objects.filter(vault__token_address=value)
        return queryset.filter(merchant__in=pos_devices.values('merchant'))