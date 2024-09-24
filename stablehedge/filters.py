from django_filters import rest_framework as filters


class RedemptionContractFilter(filters.FilterSet):
    currencies = filters.CharFilter(method="currencies_filter")
    auth_token_id = filters.CharFilter()
    price_oracle_pubkey = filters.CharFilter()
    token_category = filters.CharFilter(field_name="fiat_token__category")

    def currencies_filter(self, queryset, name, value):
        return queryset.filter(fiat_token__currency__in=str(value).split(","))
