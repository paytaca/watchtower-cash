from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response
from django.http import Http404
from django.core.exceptions import ValidationError

from rampp2p.models import (
    TradeType,
    AppealType,
    StatusType,
    Peer,
    Order
)

from rampp2p.serializers import StatusSerializer, AppealSerializer
from rampp2p.viewcodes import ViewCode
from rampp2p.validators import *
from rampp2p.utils import auth

class AppealCancel(APIView):
    def post(self, request, pk):
        try:
            # validate signature
            signature, timestamp, wallet_hash = auth.get_verification_headers(request)
            message = ViewCode.APPEAL_CANCEL.value + '::' + timestamp
            auth.verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            validate_status_inst_count(StatusType.CANCEL_APPEALED, pk)
            validate_status_confirmed(pk)
            validate_status_progression(StatusType.CANCEL_APPEALED, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        # create and Appeal record with type=CANCEL
        submit_appeal(AppealType.CANCEL, wallet_hash, pk)

        # create CANCEL_APPEALED status for order
        serializer = StatusSerializer(data={
            'status': StatusType.CANCEL_APPEALED,
            'order': pk
        })

        if serializer.is_valid():
            stat = StatusSerializer(serializer.save())
            return Response(stat.data, status=status.HTTP_200_OK)        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
  
    def validate_permissions(self, wallet_hash, pk):
        '''
        AppealCancel should be callable by the crypto buyer only
        '''

        # if ad type is SELL:
        #   order creator is BUYER
        # else (if BUY):
        #   ad owner is BUYER
        # require(caller is buyer)

        try:
            order = Order.objects.get(pk=pk)
            caller = Peer.objects.get(wallet_hash=wallet_hash)
        except Order.DoesNotExist or Peer.DoesNotExist:
            raise ValidationError('order or peer does not exist')
        
        buyer = None
        if order.ad.trade_type == TradeType.BUY:
           buyer = order.ad.owner
        else:
           buyer = order.owner

        if buyer.wallet_hash != caller.wallet_hash:
           raise ValidationError('caller must be buyer')
    
class AppealRelease(APIView):
    def post(self, request, pk):
        try:
            # validate signature
            signature, timestamp, wallet_hash = auth.get_verification_headers(request)
            message = ViewCode.APPEAL_RELEASE.value + '::' + timestamp
            auth.verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            validate_status_inst_count(StatusType.RELEASE_APPEALED, pk)
            validate_status_progression(StatusType.RELEASE_APPEALED, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        # create and Appeal record with type=RELEASE
        submit_appeal(AppealType.RELEASE, wallet_hash, pk)

        # create RELEASE_APPEALED status for order
        serializer = StatusSerializer(data={
            'status': StatusType.RELEASE_APPEALED,
            'order': pk
        })

        if serializer.is_valid():
            stat = StatusSerializer(serializer.save())
            return Response(stat.data, status=status.HTTP_200_OK)        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        AppealRelease is callable only by the crypto buyer.
        '''

        # if ad type is SELL:
        #   order creator is BUYER
        # else (if BUY):
        #   ad owner is BUYER
        # require(caller is buyer)

        try:
            order = Order.objects.get(pk=pk)
            caller = Peer.objects.get(wallet_hash=wallet_hash)
        except Order.DoesNotExist or Peer.DoesNotExist:
            raise ValidationError('order or peer does not exist')
        
        buyer = None
        if order.ad.trade_type == TradeType.BUY:
           buyer = order.ad.owner
        else:
           buyer = order.owner

        if buyer.wallet_hash != caller.wallet_hash:
           raise ValidationError('caller must be buyer')

class AppealRefund(APIView):
    def post(self, request, pk):
        try:
            # validate signature
            signature, timestamp, wallet_hash = auth.get_verification_headers(request)
            message = ViewCode.APPEAL_REFUND.value + '::' + timestamp
            auth.verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            validate_status_inst_count(StatusType.REFUND_APPEALED, pk)
            validate_status_progression(StatusType.REFUND_APPEALED, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        # create and Appeal record with type=REFUND
        submit_appeal(AppealType.REFUND, wallet_hash, pk)

        # create RELEASE_APPEALED status for order
        serializer = StatusSerializer(data={
            'status': StatusType.REFUND_APPEALED,
            'order': pk
        })

        if serializer.is_valid():
            stat = StatusSerializer(serializer.save())
            return Response(stat.data, status=status.HTTP_200_OK)        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        AppealRefund is callable only by the crypto seller.
        '''
        
        # if ad type is SELL:
        #   ad owner is SELLER
        # else (if BUY):
        #   order creator is SELLER
        # require(caller is seller)

        try:
            order = Order.objects.get(pk=pk)
            caller = Peer.objects.get(wallet_hash=wallet_hash)
        except Order.DoesNotExist or Peer.DoesNotExist:
            raise ValidationError('order or peer does not exist')
        
        seller = None
        if order.ad.trade_type == TradeType.SELL:
           seller = order.ad.owner
        else:
           seller = order.owner

        if seller.wallet_hash != caller.wallet_hash:
           raise ValidationError('caller must be seller')


def submit_appeal(type, wallet_hash, order_id):
    peer = Peer.objects.get(wallet_hash=wallet_hash)
    data = {
        'type': type, 
        'creator': peer.id,
        'order': order_id
    }
    serializer = AppealSerializer(data=data)
    if serializer.is_valid():
        appeal = serializer.save()
        return appeal
    return None