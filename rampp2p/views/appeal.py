from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response
from django.http import Http404
from django.core.exceptions import ValidationError

from ..base_models import (
  AppealType,
  StatusType,
  Peer
)

from ..base_serializers import (
  StatusSerializer,
  AppealSerializer
)

from ..validators import *

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
      validate_status_inst_count(StatusType.RELEASED, order_id)
      validate_status_confirmed(order_id)
      validate_status_progression(StatusType.CANCEL_APPEALED, order_id)
    except ValidationError as err:
      return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    # create and Appeal record with type=CANCEL
    submit_appeal(AppealType.CANCEL, wallet_hash, order_id)

    # create CANCEL_APPEALED status for order
    serializer = StatusSerializer(data={
      'status': StatusType.CANCEL_APPEALED,
      'order': order_id
    })

    if serializer.is_valid():
      stat = StatusSerializer(serializer.save())
      return Response(stat.data, status=status.HTTP_200_OK)        
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

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
      validate_status_inst_count(StatusType.RELEASED, order_id)
      validate_status_confirmed(order_id)
      validate_status_progression(StatusType.RELEASE_APPEALED, order_id)
    except ValidationError as err:
      return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    # create and Appeal record with type=RELEASE
    submit_appeal(AppealType.RELEASE, wallet_hash, order_id)

    # create RELEASE_APPEALED status for order
    serializer = StatusSerializer(data={
      'status': StatusType.RELEASE_APPEALED,
      'order': order_id
    })

    if serializer.is_valid():
      stat = StatusSerializer(serializer.save())
      return Response(stat.data, status=status.HTTP_200_OK)        
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
      validate_status_inst_count(StatusType.RELEASED, order_id)
      validate_status_confirmed(order_id)
      validate_status_progression(StatusType.REFUND_APPEALED, order_id)
    except ValidationError as err:
      return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    # create and Appeal record with type=REFUND
    submit_appeal(AppealType.REFUND, wallet_hash, order_id)

    # create RELEASE_APPEALED status for order
    serializer = StatusSerializer(data={
      'status': StatusType.REFUND_APPEALED,
      'order': order_id
    })

    if serializer.is_valid():
      stat = StatusSerializer(serializer.save())
      return Response(stat.data, status=status.HTTP_200_OK)        
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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