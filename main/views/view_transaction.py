from django.db.models.functions import Coalesce
from django.http import HttpResponse
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


TRUE_VALUES = ('1', 'true', 'yes')


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
        raw = request.query_params.get('raw', '').lower() in TRUE_VALUES
        include_hex = raw or request.query_params.get('include_hex', '').lower() in TRUE_VALUES

        txn = None
        if txid:
            node = Node()
            txn = node.BCH.get_transaction(txid, include_hex=include_hex)

        if raw:
            # Kept compatible with ElectrumNetworkProvider.getRawTransaction(), so this
            # endpoint can be used as a direct alternative to an electrum network provider.
            if not txn or not txn.get('hex'):
                return HttpResponse('', content_type='text/plain', status=status.HTTP_404_NOT_FOUND)
            return HttpResponse(txn['hex'], content_type='text/plain')

        response = {
            'valid': bool(txn),
            'details': txn or {},
        }

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
