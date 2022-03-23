from rest_framework import viewsets, mixins

from smartbch.models import (
    TransactionTransfer,
)
from smartbch.serializers import (
    TransactionTransferSerializer,
)
from smartbch.filters import TransactionTransferViewsetFilter
from smartbch.pagination import CustomLimitOffsetPagination

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
        ).all()
