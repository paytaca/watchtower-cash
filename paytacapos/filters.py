from django_filters import rest_framework as filters

from .models import *
from django.db.models import Q, OuterRef


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
        return queryset.exclude(
            Q(pubkey__isnull=value) |
            Q(index__isnull=value)
        )

class PosWalletHistoryFilter(filters.FilterSet):
    asset_id = filters.CharFilter(method="asset_id_filter")
    posid = filters.NumberFilter(method="posid_filter")
    type = filters.CharFilter(field_name="record_type")
    txids = filters.CharFilter(method="txids_filter")
    reference = filters.CharFilter(field_name="txid", lookup_expr="startswith")
    include_attrs = filters.BooleanFilter(method="include_attrs_filter")

    def posid_filter(self, queryset, name, value):
        return queryset.filter(pos_wallet_history__posid=value)

    def asset_id_filter(self, queryset, name, value):
        if value == "bch":
            return queryset.filter(cashtoken_ft__isnull=True, cashtoken_nft__isnull=True)
        return queryset.filter(Q(cashtoken_ft_id=value) | Q(cashtoken_nft_id=value))

    def txids_filter(self, queryset, name, value):
        if isinstance(value, str) and value:
            txids = [txid.strip() for txid in value.split(",") if txid]
            return queryset.filter(txid__in=txids)
        return queryset

    def include_attrs_filter(self, queryset, name, value):
        if value:
            return queryset.annotate_attributes(
                Q(wallet_hash="") | Q(wallet_hash=OuterRef("wallet__wallet_hash")),
            )
        return queryset
