from django_filters import rest_framework as filters

from vouchers.models import Voucher
from paytacapos.models import PosDevice
from main.models import CashNonFungibleToken


class VoucherFilter(filters.FilterSet):
    wallet_hash = filters.CharFilter(
        help_text='Filter vouchers by wallet hash of user',
        method='filter_wallet_hash'
    )
    merchant = filters.CharFilter(
        help_text='Filter vouchers by merchant ID',
        method='filter_merchant'
    )

    class Meta:
        model = Voucher
        fields = [
            'wallet_hash',
            'merchant',
            'claimed',
            'expired',
        ]

    def filter_merchant(self, queryset, name, value):
        pos_devices = PosDevice.objects.filter(merchant__id=merchant)
        queryset = queryset.filter(vault__pos_device__in=pos_devices)
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
        nft_commitments = list(
            nfts.values_list(
                'commitment',
                flat=True
            )
        )
        filtered_queryset = queryset.filter(
            category__in=nft_categories,
            commitment__in=nft_commitments
        )

        return filtered_queryset
