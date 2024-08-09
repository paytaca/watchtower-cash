from rest_framework.decorators import action
from rest_framework import viewsets, mixins, status
from rest_framework.response import Response

from drf_yasg.utils import swagger_auto_schema
from django_filters import rest_framework as filters
from django.core.exceptions import ImproperlyConfigured
from django.db.models import F, Q, ExpressionWrapper, DateTimeField
from django.utils import timezone

from vouchers.serializers import *
from vouchers.models import Voucher
from vouchers.filters import VoucherFilter
from vouchers.utils import verify_voucher

from paytacapos.serializers import MerchantListSerializer
from paytacapos.pagination import CustomLimitOffsetPagination
from paytacapos.models import Merchant, PosDevice 

from main.utils.queries.node import Node
from main.utils.address_converter import bch_address_converter
from main.models import CashNonFungibleToken
from main.serializers import EmptySerializer

from datetime import timedelta


class VoucherViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
):
    queryset = Voucher.objects.annotate(
        __expiration_date=ExpressionWrapper(
            F('date_created') + (timedelta(days=1) * F('duration_days')),
            output_field=DateTimeField()
        )
    ).order_by(
        '__expiration_date',
        'value'
    )
    serializer_class = EmptySerializer
    filter_class = (filters.DjangoFilterBackend, )
    filterset_class = VoucherFilter
    pagination_class = CustomLimitOffsetPagination
    serializer_classes = {
        'list': VoucherSerializer,
        'merchants': MerchantListSerializer,
        'claim_check': VoucherClaimCheckSerializer,
    }

    def list(self, request, *args, **kwargs):
        query_params = self.request.query_params
        queryset = self.filter_queryset(self.get_queryset())

        has_pagination = True
        if 'has_pagination' in query_params.keys():
            if query_params['has_pagination'].lower() == 'false':
                has_pagination = False

        if has_pagination:
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
                transaction__wallet__wallet_hash=wallet_hash,
                transaction__spent=False
            ).distinct()

        pos_devices = PosDevice.objects.filter(
            vault__vouchers__category__in=voucher_nfts.values('category'),
            vault__vouchers__commitment__in=voucher_nfts.values('commitment')
        ).distinct()

        voucher_merchants = Merchant.objects.filter(id__in=pos_device.values('merchant'))

        page = self.paginate_queryset(voucher_merchants)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(voucher_merchants, many=True)
        return Response(serializer.data)


    @action(methods=['POST'], detail=False)
    @swagger_auto_schema(responses={200: VoucherClaimCheckResponseSerializer})
    def verify(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = verify_voucher(**serializer.validated_data)
        return Response(result, status=status.HTTP_200_OK)
        

    def get_serializer_class(self):
        if not isinstance(self.serializer_classes, dict):
            raise ImproperlyConfigured("serializer_classes should be a dict mapping.")

        if self.action in self.serializer_classes.keys():
            return self.serializer_classes[self.action]
        return super().get_serializer_class()
