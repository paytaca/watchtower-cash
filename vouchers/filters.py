from django_filters import rest_framework as filters

from vouchers.models import Voucher


class VoucherFilter(filters.FilterSet):
    wallet_hash = filters.BooleanFilter(help_text='Filter vouchers by wallet hash of user')
    vault_address = filters.CharFilter(help_text='Filter vouchers by merchant using either its token or cash address')

    class Meta:
        model = Voucher
        fields = [
            'wallet_hash',
            'vault_address',
            'key_category',
            'lock_category',
            'used',
            'expired',
        ]
