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
        validate_confirm_order_perm(wallet_hash, order_id)
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
        # validate permission
        validate_buyer_confirm_payment_perm(wallet_hash, order_id)
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
        # TODO: verify permission
        validate_seller_confirm_payment_perm(wallet_hash, order_id)
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

# ReleaseCrypto is called by the crypto seller or arbiter.
class ReleaseCrypto(APIView):
  def post(self, request):
    # TODO verify signature
    # TODO verify permissions

    order_id = request.data.get('order_id', None)
    if order_id is None:
      raise Http404
    
    # TODO escrow_release()

    try:
        validate_status_inst_count(StatusType.RELEASED, order_id)
        validate_exclusive_stats(StatusType.RELEASED, order_id)
        validate_status_progression(StatusType.RELEASED, order_id)
    except ValidationError as err:
      return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
  
    # create RELEASED status for order
    serializer = StatusSerializer(data={
      'status': StatusType.RELEASED,
      'order': order_id
    })

    if serializer.is_valid():
      stat = StatusSerializer(serializer.save())
      return Response(stat.data, status=status.HTTP_200_OK)        
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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