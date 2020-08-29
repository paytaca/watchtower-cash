# Token Model ViewSet

from main.models import Transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from main.serializers import TransactionSerializer

class TransactionViewSet(viewsets.ModelViewSet):
    """
    A viewset that provides the standard actions
    """
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    http_method_names = ['get', 'head']
    lookup_field = "txid"
