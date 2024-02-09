from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import generics
from rest_framework import status
from main import serializers
from main.models import TransactionBroadcast
from main.utils.queries.node import Node
from main.tasks import broadcast_transaction

NODE = Node()

class BroadcastViewSet(generics.GenericAPIView):
    serializer_class = serializers.BroadcastSerializer
    permission_classes = [AllowAny,]

    def post(self, request, format=None):
        serializer = self.get_serializer(data=request.data)
        response = {'success': False}
        if serializer.is_valid():
            transaction = serializer.data['transaction']
            if NODE.BCH.get_latest_block(): # check if node is up
                test_accept = NODE.BCH.test_mempool_accept(transaction)
                txid = test_accept['txid']
                if test_accept['allowed']:
                    txn_broadcast = TransactionBroadcast(
                        txid=txid,
                        tx_hex=transaction
                    )
                    txn_broadcast.save()
                    broadcast_transaction.delay(transaction, txid, txn_broadcast.id)
                    response['txid'] = txid
                    response['success'] = True
                else:
                    response['error'] = test_accept['reject-reason']
                return Response(response, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
