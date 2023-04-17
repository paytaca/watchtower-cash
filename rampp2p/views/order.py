from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import Http404
from django.core.exceptions import ValidationError
from django.db.models import Q

from ..permissions import *
from ..validators import *
from ..base_serializers import (
  OrderSerializer, 
  OrderWriteSerializer, 
  StatusSerializer
)

from ..base_models import (
  Ad,
  StatusType,
  Status,
  Order,
  Peer
)

'''
  SUBMITTED         = at Order creation
  CONFIRMED         = when crypto is escrowed
  PAID_PENDING      = when crypto buyer clicks "confirm payment"
  PAID              = when crypto seller clicks on "confirm payment"
  CANCEL_APPEALED   = on cancel appeal
  RELEASE_APPEALED  = on release appeal
  REFUND_APPEALED   = on refund appeal
  RELEASED          = on arbiter "release"
  REFUNDED          = on arbiter "refunded"
  CANCELED          = on "cancel order" before status=CONFIRMED || on arbiter "mark canceled, refund"
'''

class OrderList(APIView):

  def get(self, request):
    queryset = Order.objects.all()
    creator = request.query_params.get("creator", None)
    if creator is not None:
      queryset = queryset.filter(creator=creator)
    serializer = OrderSerializer(queryset, many=True)
    return Response(serializer.data, status.HTTP_200_OK)

  def post(self, request):

    # TODO: verify signature
    # TODO: autofill order creator

    data = request.data
    ad_id = data.get('ad', None)
    if ad_id is None:
      return Response({'error': 'ad_id field is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    ad = Ad.objects.get(pk=ad_id)
    data['crypto_currency'] = ad.crypto_currency.id
    data['fiat_currency'] = ad.fiat_currency.id
    serializer = OrderWriteSerializer(data=data)
    
    if serializer.is_valid():
      order = serializer.save()

      Status.objects.create(
        status=StatusType.SUBMITTED,
        order=Order.objects.get(pk=order.id)
      )
      
      serializer = OrderSerializer(order)
      return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class OrderStatusList(APIView):
  def get(self, request, order_id):
    queryset = Status.objects.filter(order=order_id)
    serializer = StatusSerializer(queryset, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

class OrderDetail(APIView):
  def get_object(self, pk):
    try:
      return Order.objects.get(pk=pk)
    except Order.DoesNotExist:
      raise Http404

  def get(self, request, pk):
    order = self.get_object(pk)
    serializer = OrderSerializer(order)
    return Response(serializer.data, status=status.HTTP_200_OK)

  def put(self, request, pk):

    # TODO: verify signature    
    # try:
    #   verify_signature(request)
    # except ValidationError as err:
    #   return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
    # TODO: verify permission

    order = self.get_object(pk)
    serializer = OrderSerializer(order, data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ConfirmOrder(APIView):

    def post(self, request):

        # TODO: verify signature

        order_id = request.data.get('order_id', None)
        if order_id is None:
            raise Http404
        
        wallet_hash = request.data.get('wallet_hash', None)
        if order_id is None:
            raise Http404

        try:
            # validate permissions
            self.validate_permissions(wallet_hash, order_id)
            # status validations
            validate_status_inst_count(StatusType.CONFIRMED, order_id)
            validate_status_progression(StatusType.CONFIRMED, order_id)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        # TODO: escrow funds
        # escrow_funds(request.data)

        # create CONFIRMED status for order
        serializer = StatusSerializer(data={
            'status': StatusType.CONFIRMED,
            'order': order_id
        })

        if serializer.is_valid():
            stat = StatusSerializer(serializer.save())
            return Response(stat.data, status=status.HTTP_200_OK)        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def validate_permissions(self, wallet_hash, order_id):
        '''
        Only owners of SELL ads can set order statuses to CONFIRMED.
        Creators of SELL orders skip the order status to CONFIRMED on creation.
        '''

        # check if ad type is SELL
        # if ad type is SELL:
        #    require caller = ad owner
        # else
        #    raise error

        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=order_id)
        except Peer.DoesNotExist or Order.DoesNotExist:
            raise ValidationError('Peer/Order DoesNotExist')

        if order.ad.trade_type == TradeType.SELL:
            seller = order.ad.owner
            # require caller is seller
            if caller.wallet_hash != seller.wallet_hash:
                raise ValidationError('caller must be seller')
        else:
            raise ValidationError('ad trade_type is not {}'.format(TradeType.SELL))
  
class CryptoBuyerConfirmPayment(APIView):
  def post(self, request):

    # TODO: verify signature

    order_id = request.data.get('order_id', None)
    if order_id is None:
      raise Http404
    
    wallet_hash = request.data.get('wallet_hash', None)
    if wallet_hash is None:
      raise Http404
    
    try:
        self.validate_permissions(wallet_hash, order_id)
        # status validations
        validate_status_inst_count(StatusType.PAID_PENDING, order_id)
        validate_status_progression(StatusType.PAID_PENDING, order_id)
    except ValidationError as err:
      return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    # create PAID_PENDING status for order
    serializer = StatusSerializer(data={
      'status': StatusType.PAID_PENDING,
      'order': order_id
    })

    if serializer.is_valid():
      stat = StatusSerializer(serializer.save())
      return Response(stat.data, status=status.HTTP_200_OK)        
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
  
  def validate_permissions(self, wallet_hash, order_id):
    '''
    Only buyers can set order status to PAID_PENDING
    '''

    # if ad.trade_type is SELL
    #   buyer is the BUY order creator
    # else (ad.trade_type is BUY)
    #   buyer is the ad creator
    # require(caller = buyer)

    try:
        caller = Peer.objects.get(wallet_hash=wallet_hash)
        order = Order.objects.get(pk=order_id)
    except Peer.DoesNotExist or Order.DoesNotExist:
        raise ValidationError('Peer/Order DoesNotExist')
    
    buyer = None
    if order.ad.trade_type == TradeType.SELL:
       buyer = order.creator
    else:
       buyer = order.ad.owner

    if caller.wallet_hash != buyer.wallet_hash:
        raise ValidationError('caller must be buyer')
    
class CryptoSellerConfirmPayment(APIView):
    def post(self, request):
        # TODO: verify signature

        order_id = request.data.get('order_id', None)
        if order_id is None:
            raise Http404
        
        wallet_hash = request.data.get('wallet_hash', None)
        if wallet_hash is None:
            raise Http404
        
        try:
            self.validate_permissions(wallet_hash, order_id)
            # status validations
            validate_status_inst_count(StatusType.PAID, order_id)
            validate_status_progression(StatusType.PAID, order_id)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        # create PAID status for order
        serializer = StatusSerializer(data={
        'status': StatusType.PAID,
        'order': order_id
        })

        if serializer.is_valid():
            stat = StatusSerializer(serializer.save())
            return Response(stat.data, status=status.HTTP_200_OK)        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
  
    def validate_permissions(self, wallet_hash, order_id):
        '''
        Only the seller can set the order status to PAID
        '''

        # if ad.trade_type is SELL:
        #      seller is ad creator
        # else 
        #      seller is order creator
        # require(caller == seller)

        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=order_id)
        except Peer.DoesNotExist or Order.DoesNotExist:
            raise ValidationError('Peer/Order DoesNotExist')
        
        seller = None
        if order.ad.trade_type == TradeType.SELL:
            seller = order.ad.owner
        else:
            seller = order.creator

        if caller.wallet_hash != seller.wallet_hash:
            raise ValidationError('caller must be seller')

# ReleaseCrypto is called by the crypto seller or arbiter.
class ReleaseCrypto(APIView):
    def post(self, request):

        # TODO verify signature

        order_id = request.data.get('order_id', None)
        if order_id is None:
            raise Http404

        wallet_hash = request.data.get('wallet_hash', None)
        if wallet_hash is None:
            raise Http404

        try:
            # status validations
            validate_status_inst_count(StatusType.RELEASED, order_id)
            validate_exclusive_stats(StatusType.RELEASED, order_id)
            validate_status_progression(StatusType.RELEASED, order_id)
            # validate permissions
            self.validate_permissions(wallet_hash, order_id)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
    
        # TODO escrow_release()

        # create RELEASED status for order
        serializer = StatusSerializer(data={
            'status': StatusType.RELEASED,
            'order': order_id
        })

        if serializer.is_valid():
            stat = StatusSerializer(serializer.save())
            return Response(stat.data, status=status.HTTP_200_OK)        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def validate_permissions(self, wallet_hash, order_id):
        '''
        ReleaseCrypto must only be callable by seller
        or arbiter if order's status is RELEASE_APPEALED or REFUND_APPEALED
        '''

        # if caller == order.arbiter
        #   require(order.status is RELEASE_APPEALED or REFUND_APPEALED)
        # else if order.trade_type is SELL
        #   seller is ad creator
        # else
        #   seller is order creator
        # require(caller = seller)

        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=order_id)
            curr_status = Status.objects.filter(order=order).latest('created_at')
        except Peer.DoesNotExist or Order.DoesNotExist:
            raise ValidationError('Peer/Order DoesNotExist')
        
        seller = None
        if caller.wallet_hash == order.arbiter.wallet_hash:
           if (curr_status.status != StatusType.RELEASE_APPEALED and 
               curr_status.status != StatusType.REFUND_APPEALED):
              raise ValidationError('arbiter intervention but no order release/refund appeal')
        elif order.ad.trade_type == TradeType.SELL:
            seller = order.ad.owner
        else:
            seller = order.creator
        
        if seller is not None and seller.wallet_hash != caller.wallet_hash:
           raise ValidationError('caller must be seller')
           

# RefundCrypto is callable only by the arbiter
class RefundCrypto(APIView):
  def post(self, request):
    # TODO verify signature
    # TODO verify permissions

    order_id = request.data.get('order_id', None)
    if order_id is None:
        raise Http404
    
    # TODO escrow_refund()

    try:
        validate_status_inst_count(StatusType.REFUNDED, order_id)
        validate_exclusive_stats(StatusType.REFUNDED, order_id)
        validate_status_progression(StatusType.REFUNDED, order_id)
    except ValidationError as err:
        return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
  
    # create REFUNDED status for order
    serializer = StatusSerializer(data={
        'status': StatusType.REFUNDED,
        'order': order_id
    })

    if serializer.is_valid():
        stat = StatusSerializer(serializer.save())
        return Response(stat.data, status=status.HTTP_200_OK)        
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)