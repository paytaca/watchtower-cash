from django_filters import rest_framework as filters


class RedemptionContractFilter(filters.FilterSet):
    currencies = filters.CharFilter(method="currencies_filter")
    auth_token_id = filters.CharFilter()
    price_oracle_pubkey = filters.CharFilter()
    token_category = filters.CharFilter(field_name="fiat_token__category")

    def currencies_filter(self, queryset, name, value):
        return queryset.filter(fiat_token__currency__in=str(value).split(","))


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
            if self.is_valid_value_for_field("resolved_at", field):
                queryset = queryset.annotate_last_message_timestamp()
                if field.startswith("-"):
                    value[index] = F("resolved_at").desc(nulls_last=True)

        return super().filter(queryset, value)

class RedemptionContractTransactionFilter(filters.FilterSet):
    wallet_hashes = filters.CharFilter(method="wallet_hashes_filter")
    statuses = filters.CharFilter(method="statuses_filter")
    transaction_types = filters.CharFilter(method="transaction_types_filter")
    redemption_contract_address = filters.CharFilter(field_name="redemption_contract__address")
    resolved = filters.BooleanFilter(field_name='resolved_at', lookup_expr='isnull', exclude=True)
    ordering = RedemptionContractOrderingFilterField(
        fields=(
            ('id', 'id'),
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
