from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import generics
from rest_framework import status
from rest_framework.views import APIView
from main import serializers
from main.models import TransactionBroadcast, AssetPriceLog
from main.utils.broadcast import send_post_broadcast_notifications
from main.utils.queries.node import Node
from main.tasks import broadcast_transaction
import logging

NODE = Node()
LOGGER = logging.getLogger(__name__)

class BroadcastViewSet(generics.GenericAPIView):
    serializer_class = serializers.BroadcastSerializer
    permission_classes = [AllowAny,]

    def post(self, request, format=None):
        serializer = self.get_serializer(data=request.data)
        response = {'success': False}
        if serializer.is_valid():
            transaction = serializer.data['transaction']
            price_id = serializer.data.get('price_id', None)
            output_fiat_amounts = serializer.data.get('output_fiat_amounts', None)
            
            # Resolve price_log from price_id
            price_log = None
            if price_id:
                try:
                    price_log = AssetPriceLog.objects.get(id=price_id)
                except AssetPriceLog.DoesNotExist:
                    LOGGER.warning(f"price_id {price_id} not found")
            
            if NODE.BCH.get_latest_block(): # check if node is up
                test_accept = NODE.BCH.test_mempool_accept(transaction)
                txid = test_accept['txid']
                if test_accept['allowed']:
                    txn_broadcast = TransactionBroadcast(
                        txid=txid,
                        tx_hex=transaction,
                        price_log=price_log,
                        output_fiat_amounts=output_fiat_amounts
                    )
                    txn_broadcast.save()
                    broadcast_transaction.delay(transaction, txid, txn_broadcast.id)
                    send_post_broadcast_notifications(transaction)
                    response['txid'] = txid
                    response['success'] = True
                else:
                    response['error'] = test_accept['reject-reason']
                return Response(response, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TransactionOutputFiatAmountsView(APIView):
    """
    API endpoint to save output fiat amounts to an existing transaction broadcast record.
    This is typically called after a transaction has been successfully broadcast.
    """
    permission_classes = [AllowAny]
    
    def post(self, request, format=None):
        """Save fiat amounts to an existing transaction broadcast"""
        serializer = serializers.TransactionOutputFiatAmountsSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        txid = serializer.validated_data['txid']
        output_fiat_amounts = serializer.validated_data['output_fiat_amounts']
        
        try:
            txn_broadcast = TransactionBroadcast.objects.get(txid=txid)
        except TransactionBroadcast.DoesNotExist:
            return Response(
                {'success': False, 'error': f'Transaction broadcast with txid {txid} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Security check: Only allow saving if data doesn't exist yet
        if txn_broadcast.output_fiat_amounts:
            return Response(
                {
                    'success': False,
                    'error': 'Output fiat amounts already exist for this transaction. Cannot overwrite.',
                    'existing_data': txn_broadcast.output_fiat_amounts
                },
                status=status.HTTP_409_CONFLICT
            )
        
        # Update the output_fiat_amounts
        txn_broadcast.output_fiat_amounts = output_fiat_amounts
        txn_broadcast.save()
        
        LOGGER.info(f"Saved output fiat amounts for txid: {txid}")
        
        return Response({
            'success': True,
            'txid': txid,
            'message': 'Output fiat amounts saved successfully'
        }, status=status.HTTP_200_OK)
    
    def get(self, request, txid=None, format=None):
        """Retrieve output fiat amounts for a transaction"""
        if not txid:
            return Response(
                {'success': False, 'error': 'txid parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            txn_broadcast = TransactionBroadcast.objects.get(txid=txid)
        except TransactionBroadcast.DoesNotExist:
            return Response(
                {'success': False, 'error': f'Transaction broadcast with txid {txid} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response({
            'success': True,
            'txid': txid,
            'output_fiat_amounts': txn_broadcast.output_fiat_amounts
        }, status=status.HTTP_200_OK)
