# from drf_yasg import openapi
# from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets, mixins
# from rest_framework.views import APIView
# from rest_framework.response import Response
# from django.db.models import F, Subquery, OuterRef, Count, Q
from django_filters import rest_framework as filters
# from rest_framework import status

from main.filters import CashNftFilter, TokensViewSetFilter
from main.models import (
    CashFungibleToken,
    CashNonFungibleToken,
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
