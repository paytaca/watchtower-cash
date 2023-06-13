from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets, mixins, decorators
# from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import OuterRef, Q, Exists
from django_filters import rest_framework as filters
# from rest_framework import status

from main.filters import CashNftFilter, TokensViewSetFilter
from main.models import (
    CashFungibleToken,
    CashNonFungibleToken,
    Transaction,
    # WalletHistory,
    # Token,
    # WalletNftToken
)
from main.serializers import (
    CashFungibleTokenSerializer,
    CashNonFungibleTokenSerializer,
)

from smartbch.pagination import CustomLimitOffsetPagination


class CashFungibleTokensViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin
):
    queryset = CashFungibleToken.objects.all()
    serializer_class = CashFungibleTokenSerializer
    pagination_class = CustomLimitOffsetPagination

    filter_backends = [
        TokensViewSetFilter,
    ]


class CashNftsViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin
):
    queryset = CashNonFungibleToken.objects.all()
    serializer_class = CashNonFungibleTokenSerializer
    pagination_class = CustomLimitOffsetPagination

    filter_backends = [
        TokensViewSetFilter,
        filters.DjangoFilterBackend,
    ]
    filterset_class = CashNftFilter

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        queryset = self.filter_queryset(queryset)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                name="wallet_hash", type=openapi.TYPE_STRING,
                in_=openapi.IN_QUERY, required=False,
            ),
        ]
    )
    @decorators.action(detail=False, methods=["get"], filter_backends=[])
    def groups(self, request, *args, **kwargs):
        wallet_hash = request.query_params.get("wallet_hash", None)
        queryset = CashNonFungibleToken.objects.filter_group()
        if wallet_hash:
            owned_nfts_subq = CashNonFungibleToken.objects \
                .annotate_owner_wallet_hash() \
                .filter(owner_wallet_hash=wallet_hash) \
                .filter(category=OuterRef("category"))

            queryset = queryset \
                .filter(Exists(owned_nfts_subq))

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
