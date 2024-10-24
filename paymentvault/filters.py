from django_filters import rest_framework as filters

from .models import PaymentVault


class PaymentVaultFilterSet(filters.FilterSet):
    merchant_pubkey = filters.CharFilter(field_name='merchant__pubkey', lookup_expr='iexact')

    class Meta:
        model = PaymentVault
        fields = (
            'user_pubkey',
            'merchant',
            'merchant_pubkey',
            'address',
            'token_address',
        )