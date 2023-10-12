from django_filters import rest_framework as filters
from django.db.models import Q

from vouchers.models import Voucher

from main.models import CashNonFungibleToken


class VoucherFilter(filters.FilterSet):
    wallet_hash = filters.CharFilter(
        help_text='Filter vouchers by wallet hash of user',
        method='filter_wallet_hash'
    )
    vault_address = filters.CharFilter(
        help_text='Filter vouchers by merchant using either its token or cash address',
        method='filter_vault_address'
    )

    class Meta:
        model = Voucher
        fields = [
            'wallet_hash',
            'vault_address',
            'claimed',
            'expired',
        ]

    def filter_vault_address(self, queryset, name, value):
        queryset = queryset.filter(
            Q(vault__token_address=value) |
            Q(vault__address=value)
        )
        return queryset

    def filter_wallet_hash(self, queryset, name, value):
        nfts = CashNonFungibleToken.objects.filter(transaction__wallet__wallet_hash=value)
        nfts = nfts.distinct()
        nft_categories = list(
            nfts.values_list(
                'category',
                flat=True
            )
        )
        return queryset.filter(category__in=nft_categories)
