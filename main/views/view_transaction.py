from django.db.models.functions import Coalesce
from rest_framework import viewsets
from rest_framework import mixins
from rest_framework import generics
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters import rest_framework as filters

from main import models
from main.filters import TransactionOutputFilter
from main.pagination import CustomLimitOffsetPagination
from main.serializers import TransactionMetaAttributeSerializer, TransactionOutputSerializer
from main.utils.queries.node import Node


class TransactionMetaAttributeView(generics.GenericAPIView):
    serializer_class = TransactionMetaAttributeSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if not serializer.instance:
            return Response()

        return Response(serializer.data)


class TransactionDetailsView(APIView):

    def get(self, request, *args, **kwargs):
        txid = kwargs.get('txid', '')
        response = {
            'valid': False,
            'details': {}
        }

        if txid:
            node = Node()
            txn = node.BCH.get_transaction(txid)
            response['valid'] = True
            response['details'] = txn

        return Response(response, status=status.HTTP_200_OK)


class TransactionOutputViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
):
    serializer_class = TransactionOutputSerializer
    pagination_class = CustomLimitOffsetPagination

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = TransactionOutputFilter

    def get_queryset(self):
        return models.Transaction.objects.select_related("token", "cashtoken_nft", "address") \
            .annotate(
                category=Coalesce("cashtoken_nft__category", "cashtoken_ft__category"),
                decimals=Coalesce("cashtoken_nft__info__decimals", "cashtoken_ft__info__decimals"),
                token_ticker=Coalesce("cashtoken_nft__info__symbol", "cashtoken_ft__info__symbol")
            )
