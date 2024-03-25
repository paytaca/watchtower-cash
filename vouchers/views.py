from rest_framework.decorators import action
from rest_framework import viewsets, mixins, status
from rest_framework.response import Response

from drf_yasg.utils import swagger_auto_schema
from django_filters import rest_framework as filters
from django.core.exceptions import ImproperlyConfigured
from django.db.models import F, Q, ExpressionWrapper, DateTimeField
from django.utils import timezone

from vouchers.serializers import (
    VoucherSerializer,
    VoucherClaimCheckSerializer,
    VoucherClaimCheckResponseSerializer,
    VoucherClaimedSerializer,
    VoucherClaimedResponseSerializer,
)
from vouchers.models import Voucher
from vouchers.filters import VoucherFilter

from paytacapos.serializers import MerchantListSerializer
from paytacapos.pagination import CustomLimitOffsetPagination
from paytacapos.models import Merchant

from main.utils.queries.node import Node
from main.utils.address_converter import bch_address_converter
from main.models import CashNonFungibleToken
from main.serializers import EmptySerializer

from datetime import timedelta


class VoucherViewSet(
    viewsets.GenericViewSet,
    mixins.CreateModelMixin,
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
        'create': VoucherSerializer,
        'list': VoucherSerializer,
        'merchants': MerchantListSerializer,
        'claim_check': VoucherClaimCheckSerializer,
        'claimed': VoucherClaimedSerializer,
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


    @action(methods=['POST'], detail=False)
    @swagger_auto_schema(responses={200: VoucherClaimedResponseSerializer})
    def claimed(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        category = serializer.validated_data['category']
        claim_txid = serializer.validated_data['txid']
        vouchers = Voucher.objects.filter(category=category)
        result = { 'success': False }
        
        if vouchers.exists():
            node = Node()
            txn = node.BCH.get_transaction(claim_txid)

            if txn['valid']:
                inputs = txn['inputs']
                first_input = inputs[0]
                second_input = inputs[1]

                if 'token_data' in first_input.keys() and 'token_data' in second_input.keys():
                    voucher = vouchers.first()
                    first_input_category = first_input['token_data']['category']
                    second_input_category = second_input['token_data']['category']

                    if first_input_category == voucher.category and first_input_category == second_input_category:
                        vouchers.update(
                            claimed=True,
                            claim_txid=claim_txid,
                            date_claimed=timezone.now()
                        )
                        result['success'] = True
        
        return Response(result, status=status.HTTP_200_OK)


    @action(methods=['GET'], detail=False)
    @swagger_auto_schema(responses={200: MerchantListSerializer})
    def merchants(self, request, *args, **kwargs):
        wallet_hash = request.query_params.get('wallet_hash') or ''
        voucher_nfts = CashNonFungibleToken.objects.all()
        if wallet_hash:
            voucher_nfts = voucher_nfts.filter(
                transaction__wallet__wallet_hash=wallet_hash,
                transaction__spent=False
            )

        voucher_nfts = voucher_nfts.distinct()
        voucher_merchants = Merchant.objects.filter(
            vault__vouchers__category__in=voucher_nfts.values('category'),
            vault__vouchers__commitment__in=voucher_nfts.values('commitment')
        ).distinct()

        page = self.paginate_queryset(voucher_merchants)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(voucher_merchants, many=True)
        return Response(serializer.data)


    @action(methods=['POST'], detail=False)
    @swagger_auto_schema(responses={200: VoucherClaimCheckResponseSerializer})
    def claim_check(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # check if recipient is merchant
        vault_token_address = serializer.validated_data['address']
        merchants = Merchant.objects.filter(
            vault__token_address=vault_token_address
        )
        is_merchant_address = merchants.exists()
        result = {
            'proceed': False
        }
        
        if is_merchant_address:
            valid_categories = []
            voucher_ids = serializer.validated_data['voucher_ids']

            # error keys
            VOUCHER_EXPIRED = 'voucher_expired'
            INVALID_VOUCHER = 'invalid_voucher'
            VOUCHER_MERCHANT_MISMATCH = 'voucher_merchant_mismatch'

            for voucher_id in voucher_ids:
                vouchers = Voucher.objects.filter(id=voucher_id)
                result[voucher_id] = { 'err': '' }

                if vouchers.exists():
                    voucher = vouchers.first()
                    merchant = merchants.first()
                    voucher_belongs_to_merchant = merchant.id == voucher.vault.merchant.id

                    if voucher_belongs_to_merchant:
                        if voucher.expired:
                            result[voucher_id]['err'] = VOUCHER_EXPIRED
                            return Response(result)

                        node = Node()
                        txn = node.BCH.get_transaction(voucher.minting_txid)

                        if txn['valid']:
                            outputs = txn['outputs']
                            key_nft_output = outputs[0]
                            lock_nft_output = outputs[1]

                            lock_nft_recipient = lock_nft_output['address']
                            lock_nft_recipient = bch_address_converter(lock_nft_recipient)
                            key_nft_category = key_nft_output['token_data']['category']

                            # check if lock NFT recipient address is this endpoint payload's vault address
                            if key_nft_category == voucher.category and lock_nft_recipient == vault_token_address:
                                valid_categories.append(key_nft_category)
                            else:
                                result[voucher_id]['err'] = VOUCHER_MERCHANT_MISMATCH
                        else:
                            result[voucher_id]['err'] = INVALID_VOUCHER
                    else:
                        result[voucher_id]['err'] = VOUCHER_MERCHANT_MISMATCH
                else:
                    result[voucher_id]['err'] = INVALID_VOUCHER

            if len(valid_categories) == len(voucher_ids):
                result['proceed'] = True
        
        return Response(result, status=status.HTTP_200_OK)
        

    def get_serializer_class(self):
        if not isinstance(self.serializer_classes, dict):
            raise ImproperlyConfigured("serializer_classes should be a dict mapping.")

        if self.action in self.serializer_classes.keys():
            return self.serializer_classes[self.action]
        return super().get_serializer_class()
