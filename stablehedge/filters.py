import re
from django.db.models import F, Q
from django_filters import rest_framework as filters


class FiatTokenFilter(filters.FilterSet):
    categories = filters.CharFilter(method="categories_filter")
    currencies = filters.CharFilter(method="currencies_filter")

    def categories_filter(self, queryset, name, value):
        return queryset.filter(category__in=str(value).split(","))

    def currencies_filter(self, queryset, name, value):
        return queryset.filter(currency__in=str(value).split(","))


class RedemptionContractFilter(filters.FilterSet):
    categories = filters.CharFilter(method="categories_filter")
    currencies = filters.CharFilter(method="currencies_filter")
    auth_token_id = filters.CharFilter()
    price_oracle_pubkey = filters.CharFilter()
    token_category = filters.CharFilter(field_name="fiat_token__category")
    has_treasury_contract = filters.BooleanFilter(
        field_name="treasury_contract", lookup_expr='isnull', exclude=True,
    )
    min_redeemable = filters.NumberFilter(method="min_redeemable_filter")
    max_redeemable = filters.NumberFilter(method="max_redeemable_filter")
    min_reserve_supply = filters.NumberFilter(method="min_reserve_supply_filter")
    max_reserve_supply = filters.NumberFilter(method="max_reserve_supply_filter")
    verified = filters.BooleanFilter()

    def categories_filter(self, queryset, name, value):
        return queryset.filter(fiat_token__category__in=str(value).split(","))

    def currencies_filter(self, queryset, name, value):
        return queryset.filter(fiat_token__currency__in=str(value).split(","))

    def min_redeemable_filter(self, queryset, name, value):
        return queryset.annotate_redeemable() \
            .filter(redeemable__gte=value)

    def max_redeemable_filter(self, queryset, name, value):
        return queryset.annotate_redeemable() \
            .filter(redeemable__lte=value)

    def min_reserve_supply_filter(self, queryset, name, value):
        return queryset.annotate_reserve_supply() \
            .filter(reserve_supply__gte=value)

    def max_reserve_supply_filter(self, queryset, name, value):
        return queryset.annotate_reserve_supply() \
            .filter(reserve_supply__lte=value)


class RedemptionContractOrderingFilterField(filters.OrderingFilter):
    @classmethod
    def is_valid_value_for_field(cls, field_name, value):
        match = re.match(f"^-?{field_name}$", value)
        return bool(match)

    def get_ordering_value(self, param):
        if not isinstance(param, str): return param
        return super().get_ordering_value(param)

    def filter(self, queryset, value):
        if not value: return queryset

        for index, field in enumerate(value):
            if self.is_valid_value_for_field("status", field):
                if field.startswith("-"):
                    value[index] = F("status").desc(nulls_last=True)
            if self.is_valid_value_for_field("resolved_at", field):
                if field.startswith("-"):
                    value[index] = F("resolved_at").desc(nulls_last=True)
            if self.is_valid_value_for_field("created_at", field):
                if field.startswith("-"):
                    value[index] = F("created_at").desc(nulls_last=True)

        return super().filter(queryset, value)

class RedemptionContractTransactionFilter(filters.FilterSet):
    wallet_hashes = filters.CharFilter(method="wallet_hashes_filter")
    statuses = filters.CharFilter(method="statuses_filter")
    transaction_types = filters.CharFilter(method="transaction_types_filter")
    redemption_contract_address = filters.CharFilter(field_name="redemption_contract__address")
    resolved = filters.BooleanFilter(field_name='resolved_at', lookup_expr='isnull', exclude=True)
    categories = filters.CharFilter(method="categories_filter")
    ordering = RedemptionContractOrderingFilterField(
        fields=(
            ('id', 'id'),
            ('status', 'status'),
            ('resolved_at', 'resolved_at'),
            ('created_at', 'created_at'),
        )
    )

    def wallet_hashes_filter(self, queryset, name, value):
        return queryset.filter(wallet_hash__in=str(value).split(","))

    def statuses_filter(self, queryset, name, value):
        return queryset.filter(status__in=str(value).split(","))

    def transaction_types_filter(self, queryset, name, value):
        return queryset.filter(transaction_type__in=str(value).split(","))

    def categories_filter(self, queryset, name, value):
        return queryset.filter(redemption_contract__fiat_token__category__in=str(value).split(","))


class TreasuryContractFilter(filters.FilterSet):
    pubkeys = filters.CharFilter(method="pubkeys_filter")
    def pubkeys_filter(self, queryset, name, value):
        pubkeys = str(value).split(",")

        return queryset.filter(
            Q(pubkey1__in=pubkeys) |
            Q(pubkey2__in=pubkeys) |
            Q(pubkey3__in=pubkeys) |
            Q(pubkey4__in=pubkeys) |
            Q(pubkey5__in=pubkeys)
        )
