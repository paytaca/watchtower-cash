from django.http import Http404
from rest_framework import viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema

from smartbch.models import (
    Transaction,
    TransactionTransfer,
)
from smartbch.serializers import (
    TransactionSerializer,
    TransactionTransferSerializer,
)
from smartbch.filters import TransactionTransferViewsetFilter
from smartbch.pagination import CustomLimitOffsetPagination


class TransactionViewSet(viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    lookup_field = "txid"
    serializer_class = TransactionSerializer
    pagination_class = CustomLimitOffsetPagination

    def get_object(self):
        Model = self.serializer_class.Meta.model
        lookup_value = self.kwargs.get(self.lookup_field)
        try:
            instance = Model.objects.get(**{
                f"{self.lookup_field}__iexact": lookup_value,
            })
            return instance
        except Model.DoesNotExist:
            raise Http404
        except Model.MultipleObjectsReturned:
            pass

        return super().get_object()

    def get_queryset(self):
        return Transaction.objects.select_related(
            "block",
        ).prefetch_related(
            "transfers",
            "transfers__transaction",
            "transfers__transaction__block",
        ).order_by(
            "-block__block_number",
        ).all()

    @swagger_auto_schema(responses={ 200: TransactionTransferSerializer(many=True) })
    @action(methods=["get"], detail=True)
    def transfers(self, request, *args, **kwargs):
        obj = self.get_object()
        tx_transfers = TransactionTransfer.objects.filter(transaction__txid=obj.txid)
        serializer = TransactionTransferSerializer(tx_transfers, many=True)
        return Response(serializer.data)


class TransactionTransferViewSet(viewsets.GenericViewSet, mixins.ListModelMixin):
    serializer_class = TransactionTransferSerializer
    pagination_class = CustomLimitOffsetPagination

    filter_backends = [
        TransactionTransferViewsetFilter,
    ]

    def get_queryset(self):
        return TransactionTransfer.objects.select_related(
            "token_contract",
            "transaction",
            "transaction__block",
        ).order_by(
            "-transaction__block__block_number"
        ).all()
