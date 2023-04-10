from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from django.db.models import Q
from django.core.exceptions import ValidationError
from ..serializers.feedback import FeedbackSerializer
from ..models.peer import Peer
from ..models.feedback import Feedback

class ArbiterFeedbackListCreate(APIView):
  def get(self, request):
    queryset = Feedback.objects.filter(Q(to_peer__is_arbiter=True))

    order = request.query_params.get('order', None)
    if order is not None:
      queryset = queryset.filter(Q(order=order))

    from_peer = request.query_params.get('from_peer', None)
    if from_peer is not None:
      queryset = queryset.filter(Q(from_peer=from_peer))

    arbiter = request.query_params.get('arbiter', None)
    if arbiter is not None:
      queryset = queryset.filter(Q(from_peer=arbiter))

    rating = request.query_params.get('rating', None)
    if rating is not None:
      queryset = queryset.filter(Q(rating=rating))

    # TODO pagination

    serializer = FeedbackSerializer(queryset, many=True)
    return Response(serializer.data, status.HTTP_200_OK)

  def post(self, request):
    serializer = FeedbackSerializer(data=request.data)
    if serializer.is_valid():

      # to_peer must be arbiter
      try:
        self.validate_arbiter(
          serializer.validated_data['from_peer'], 
          serializer.validated_data['to_peer'],
          serializer.validated_data['order']
        )
      except ValidationError as err:
        return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
    
      # the no. of feedback instance of {from_peer, to_peer, order} pair must be 1.
      try:
        self.validate_limit(
          serializer.validated_data['from_peer'], 
          serializer.validated_data['to_peer'],
          serializer.validated_data['order']
        )
      except ValidationError as err:
        return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

      # peer must be allowed to create a feedback for this order
      try:
        validate_allowed(serializer.validated_data['from_peer'], serializer.validated_data['order'])
      except ValidationError as err:
        return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
      
      serializer.save()
      return Response(serializer.data, status=status.HTTP_200_OK)

    return Response({'error': 'invalid payload', 'data': serializer.data}, status=status.HTTP_400_BAD_REQUEST)
  
  def validate_arbiter(self, from_peer, to_peer, order):
    '''
    Validates if to_peer is the order's arbiter
    '''
    if from_peer == to_peer:
      raise ValidationError('to_peer must be the order\'s arbiter')
    
    if order.arbiter != to_peer:
      raise ValidationError('to_peer must be the order\'s arbiter')
    
    if to_peer.is_arbiter is False:
      raise ValidationError('to_peer must be the order\'s arbiter')
    
  def validate_limit(self, from_peer, to_peer, order):
    '''
    Validates that from_peer can only create 1 arbiter feedback for the order.
    '''
    feedback_count = (Feedback.objects.filter(
      Q(from_peer=from_peer) & 
      Q(to_peer=to_peer) & 
      Q(order=order)
    )).count()

    if feedback_count > 0:
      raise ValidationError('peer feedback already existing')
    
class PeerFeedbackListCreate(APIView):
  def get(self, request):
    queryset = Feedback.objects.filter(Q(to_peer__is_arbiter=False))
    
    order = request.query_params.get('order', None)
    if order is not None:
      queryset = queryset.filter(Q(order=order))
    
    from_peer = request.query_params.get('from_peer', None)
    if from_peer is not None:
      queryset = queryset.filter(Q(from_peer=from_peer))
    
    to_peer = request.query_params.get('to_peer', None)
    if to_peer is not None:
      queryset = queryset.filter(Q(to_peer=to_peer))
    
    rating = request.query_params.get('rating', None)
    if rating is not None:
      queryset = queryset.filter(Q(rating=rating))

    # TODO pagination

    serializer = FeedbackSerializer(queryset, many=True)
    return Response(serializer.data, status.HTTP_200_OK)

  def post(self, request):
    serializer = FeedbackSerializer(data=request.data)
    if serializer.is_valid():

      # to_peer must be arbiter
      try:
        self.validate_counterparty(
          serializer.validated_data['from_peer'], 
          serializer.validated_data['to_peer'], 
          serializer.validated_data['order'])
      except ValidationError as err:
        return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
    
      # the no. of feedback instance of {from_peer, order} pair must be 1.
      try:
        self.validate_limit(
          serializer.validated_data['from_peer'], 
          serializer.validated_data['to_peer'], 
          serializer.validated_data['order']
        )
      except ValidationError as err:
        return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

      # peer must be allowed to create a feedback for this order
      try:
        validate_allowed(serializer.validated_data['from_peer'], serializer.validated_data['order'])
      except ValidationError as err:
        return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
      
      serializer.save()
      return Response(serializer.data, status=status.HTTP_200_OK)

    return Response({'error': 'invalid payload', 'data': serializer.data}, status=status.HTTP_400_BAD_REQUEST)
  
  def validate_counterparty(self, from_peer, to_peer, order):
    '''
    Validates if to_peer is order counterparty
    '''
    if to_peer == from_peer:
      raise ValidationError('to_peer must be order counterparty')
    
    if from_peer == order.creator:
      if to_peer != order.ad.owner:
        raise ValidationError('to_peer must be order counterparty')
    
    if from_peer == order.ad.owner:
      if to_peer != order.creator:
        raise ValidationError('to_peer must be order counterparty')
    
  def validate_limit(self, from_peer, to_peer, order):
    '''
    Validates that from_peer can only create 1 feedback for the order.
    '''
    feedback_count = (Feedback.objects.filter(
      Q(from_peer=from_peer) & 
      Q(to_peer=to_peer) & 
      Q(order=order)
    )).count()

    if feedback_count > 0:
      raise ValidationError('peer feedback already existing')
    
class FeedbackDetail(generics.RetrieveUpdateAPIView):
  queryset = Feedback.objects.all()
  serializer_class = FeedbackSerializer

def validate_allowed(from_peer, order):
  '''
  Validates if from_peer is allowed to create an arbiter feedback for this order.
  '''
  # check if from_peer is order seller or buyer
  # i.e. order creator or order-ad creator
  order_creator = order.creator == from_peer
  order_ad_creator = order.ad.owner == from_peer

  if not (order_creator or order_ad_creator):
    raise ValidationError('peer not allowed to feedback this order')