from django_filters import rest_framework as filters

from vouchers.models import Voucher, PosDeviceVault, MerchantVault
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
        merchant_vaults = MerchantVault.objects.filter(merchant__id=value)
        queryset = queryset.filter(vault__in=merchant_vaults)
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


class PosDeviceVaultFilter(filters.FilterSet):
    posid = filters.NumberFilter(field_name="pos_device__posid", lookup_expr="exact")
    wallet_hash = filters.CharFilter(field_name="pos_device__wallet_hash", lookup_expr="exact")
    
    class Meta:
        model = PosDeviceVault
        fields = [
            'posid',
            'wallet_hash',
        ]