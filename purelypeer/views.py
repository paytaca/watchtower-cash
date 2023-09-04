from rest_framework.decorators import action
from rest_framework import viewsets, mixins
from rest_framework.response import Response

from drf_yasg.utils import swagger_auto_schema
from django_filters import rest_framework as filters
from django.core.exceptions import ImproperlyConfigured
from django.db.models import F

from purelypeer.serializers import CreateVoucherSerializer
from purelypeer.models import Voucher
from purelypeer.filters import VoucherFilter

from paytacapos.serializers import MerchantListSerializer
from paytacapos.pagination import CustomLimitOffsetPagination
from paytacapos.models import Merchant

from main.models import CashNonFungibleToken
from main.serializers import (
    CashNonFungibleTokenSerializer,
    EmptySerializer,
)


class VoucherViewSet(
    viewsets.GenericViewSet,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
):
    queryset = Voucher.objects.all()
    serializer_class = EmptySerializer
    filter_class = (filters.DjangoFilterBackend, )
    filterset_class = VoucherFilter
    pagination_class = CustomLimitOffsetPagination
    serializer_classes = {
        'create': CreateVoucherSerializer,
        'list': CashNonFungibleTokenSerializer,
        'merchants': MerchantListSerializer
    }

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        wallet_hash = request.query_params.get('wallet_hash') or ''
        merchant_wallet_hash = request.query_params.get('merchant_wallet_hash') or ''

        vouchers = queryset
        if merchant_wallet_hash:
            vouchers = vouchers.filter(
                vault__merchant__wallet_hash=merchant_wallet_hash
            )

        voucher_categories = list(
            vouchers.values_list(
                'key_category',
                flat=True
            )
        )
        owned_vouchers = CashNonFungibleToken.objects.filter(
            category__in=voucher_categories
        )

        if wallet_hash:
            owned_vouchers = owned_vouchers.filter(
                transaction__wallet__wallet_hash=wallet_hash
            )

        queryset = owned_vouchers.distinct()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


    @action(methods=['GET'], detail=False)
    @swagger_auto_schema(responses={200: MerchantListSerializer})
    def merchants(self, request, *args, **kwargs):
        wallet_hash = request.query_params.get('wallet_hash') or ''
        voucher_nfts = CashNonFungibleToken.objects.all()
        if wallet_hash:
            voucher_nfts = voucher_nfts.filter(
                transaction__wallet__wallet_hash=wallet_hash
            )

        voucher_nfts = voucher_nfts.distinct()
        voucher_nfts_categories = list(
            voucher_nfts.values_list(
                'category',
                flat=True
            )
        )
        voucher_merchants = Merchant.objects.filter(
            vault__vouchers__key_category__in=voucher_nfts_categories
        ).distinct()

        page = self.paginate_queryset(voucher_merchants)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(voucher_merchants, many=True)
        return Response(serializer.data)


    def get_serializer_class(self):
        if not isinstance(self.serializer_classes, dict):
            raise ImproperlyConfigured("serializer_classes should be a dict mapping.")

        if self.action in self.serializer_classes.keys():
            return self.serializer_classes[self.action]
        return super().get_serializer_class()
