from rest_framework import generics
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from main.serializers import TransactionMetaAttributeSerializer
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
