from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import generics
from rest_framework import status
from bitcash.transaction import calc_txid
from main import serializers
from main.models import Address
from main.tasks import rescan_utxos
from main.utils.queries.bchn import BCHN
from main.tasks import broadcast_transaction


class BroadcastViewSet(generics.GenericAPIView):
    serializer_class = serializers.BroadcastSerializer
    permission_classes = [AllowAny,]

    def post(self, request, format=None):
        serializer = self.get_serializer(data=request.data)
        response = {'success': False}
        if serializer.is_valid():
            transaction = serializer.data['transaction']
            txid = calc_txid(transaction)
            broadcast_transaction.delay(transaction, txid)
            response['txid'] = txid
            response['success'] = True
            return Response(response, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
