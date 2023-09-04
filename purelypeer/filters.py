from django_filters import rest_framework as filters

from purelypeer.models import Voucher


class VoucherFilter(filters.FilterSet):
    wallet_hash = filters.BooleanFilter(help_text='Filter vouchers by wallet hash of user')
    merchant_wallet_hash = filters.CharFilter(help_text='Filter vouchers by merchant')

    class Meta:
        model = Voucher
        fields = [
            'wallet_hash',
            'merchant_wallet_hash',
            'key_category',
            'lock_category',
            'used',
            'expired',
        ]
