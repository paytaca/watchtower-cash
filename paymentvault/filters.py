from django_filters import rest_framework as filters

from .models import PaymentVault


class PaymentVaultFilterSet(filters.FilterSet):
    class Meta:
        model = PaymentVault
        fields = '__all__'