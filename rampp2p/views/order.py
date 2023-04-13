from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import Http404
from django.core.exceptions import ValidationError
from django.db.models import Q

from ..base_serializers import (
  OrderSerializer, 
  OrderWriteSerializer, 
  StatusSerializer, 
  AppealSerializer
)

from ..base_models import (
  Ad,
  StatusType,
  AppealType,
  Peer,
  Status,
  Order
)

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
    # TODO: verify permission

    order_id = request.data.get('order_id', None)
    if order_id is None:
      raise Http404
    
    # TODO: escrow funds
    # escrow_funds(request.data)

    try:
        # validate status instance count
        validate_status_inst_count(StatusType.CONFIRMED, order_id)
    except ValidationError as err:
      return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    # create CONFIRMED status for order
    serializer = StatusSerializer(data={
      'status': StatusType.CONFIRMED,
      'order': order_id
    })

    if serializer.is_valid():
      stat = StatusSerializer(serializer.save())
      return Response(stat.data, status=status.HTTP_200_OK)        
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
  
class ConfirmPayment(APIView):
  def post(self, request):
    # TODO: verify signature
    # TODO: verify permission

    order_id = request.data.get('order_id', None)
    if order_id is None:
      raise Http404
    
    try:
        # validate status instance count
        validate_status_inst_count(StatusType.PAID, order_id)
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

# AppealCancel is callable by either party
# AppealCancel creates an Appeal instance with field type=CANCEL
# RESTRICTION: parties cannot appeal-cancel when an order is not marked as CONFIRMED
class AppealCancel(APIView):
  def post(self, request):
    # TODO: verify signature
    # TODO: verify permission

    order_id = request.data.get('order_id', None)
    if order_id is None:
      raise Http404
    
    wallet_hash = request.data.get('wallet_hash', None)
    if wallet_hash is None:
      return Response({'error': 'wallet_hash field is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
      validate_status_confirmed(order_id)
    except ValidationError as err:
      return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    # create and Appeal record with type=CANCEL
    submit_appeal(AppealType.CANCEL, wallet_hash, order_id)

    # update the order status to CANCEL_APPEALED
    Status.objects.create(
      status=StatusType.CANCEL_APPEALED,
      order=Order.objects.get(pk=order_id)
    )

# AppealRelease is callable only by the crypto buyer.
# AppealRelease creates an Appeal instance with field type=RELEASE
# RESTRICTION: parties cannot appeal-release when an order is not marked as CONFIRMED
class AppealRelease(APIView):
  def post(self, request):
    # TODO: verify signature
    # TODO: verify permission

    order_id = request.data.get('order_id', None)
    if order_id is None:
      raise Http404
    
    wallet_hash = request.data.get('wallet_hash', None)
    if wallet_hash is None:
      return Response({'error': 'wallet_hash field is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
      validate_status_confirmed(order_id)
    except ValidationError as err:
      return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    # create and Appeal record with type=RELEASE
    submit_appeal(AppealType.RELEASE, wallet_hash, order_id)

    # update the order status to RELEASE_APPEALED
    Status.objects.create(
      status=StatusType.RELEASE_APPEALED,
      order=Order.objects.get(pk=order_id)
    )

# AppealRefund is callable only by the crypto seller.
# AppealRefund creates an Appeal instance with field type=REFUND
# RESTRICTION: parties cannot appeal-refund when an order is not marked as CONFIRMED
class AppealRefund(APIView):
  def post(self, request):
    # TODO: verify signature
    # TODO: verify permission

    order_id = request.data.get('order_id', None)
    if order_id is None:
      raise Http404
    
    wallet_hash = request.data.get('wallet_hash', None)
    if wallet_hash is None:
      return Response({'error': 'wallet_hash field is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
      validate_status_confirmed(order_id)
    except ValidationError as err:
      return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    # create and Appeal record with type=REFUND
    submit_appeal(AppealType.REFUND, wallet_hash, order_id)

    # update the order status to REFUND_APPEALED
    Status.objects.create(
      status=StatusType.REFUND_APPEALED,
      order=Order.objects.get(pk=order_id)
    )

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

def escrow_funds(self, data):
  pass

'''
  SUBMITTED = at Order creation
  CONFIRMED = when crypto is escrowed
  PAID      = on "confirm payment"
  CANCEL_APPEALED  = on cancel appeal
  RELEASE_APPEALED = on release appeal
  REFUND_APPEALED = on refund appeal
  RELEASED  = on arbiter "release"
  REFUNDED  = on arbiter "refunded"
  CANCELED  = on "cancel order" before status=CONFIRMED || on arbiter "mark canceled, refund"
'''

def validate_status_confirmed(order_id):
    # check: current order status must be CONFIRMED
    current_status = Status.objects.filter(order=order_id).latest('created_at')
    if current_status.status != StatusType.CONFIRMED:
        raise ValidationError('action not allowed')
  
def validate_status_inst_count(status, order_id):
    status_count = Status.objects.filter(Q(order=order_id) & Q(status=status)).count()
    if status_count > 0:
        raise ValidationError('duplicate status')
    
def validate_exclusive_stats(status, order_id):
    if status == StatusType.RELEASED:
        stat_count = Status.objects.filter(Q(order=order_id) & Q(status=StatusType.REFUNDED)).count()
        if stat_count > 0:
            raise ValidationError('cannot release what is already refunded')
    
    if status == StatusType.REFUNDED:
        stat_count = Status.objects.filter(Q(order=order_id) & Q(status=StatusType.RELEASED)).count()
        if stat_count > 0:
            raise ValidationError('cannot refund what is already released')
