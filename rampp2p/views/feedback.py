from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from django.db.models import Q
from django.core.exceptions import ValidationError

from rampp2p.utils.signature import verify_signature, get_verification_headers
from rampp2p.models import Feedback, Peer, Order, ArbiterFeedback
from rampp2p.serializers import (
    FeedbackSerializer, 
    ArbiterFeedbackSerializer, 
    ArbiterFeedbackCreateSerializer
)
from rampp2p.viewcodes import ViewCode

import logging
logger = logging.getLogger(__name__)

class ArbiterFeedbackListCreate(APIView):
    def get(self, request):
        queryset = ArbiterFeedback.objects.all()

        order = request.query_params.get('order')
        from_peer = request.query_params.get('from_peer')
        arbiter = request.query_params.get('arbiter')
        rating = request.query_params.get('rating')

        if order is not None:
            queryset = queryset.filter(Q(order=order))
        
        if from_peer is not None:
            queryset = queryset.filter(Q(from_peer=from_peer))
        
        if arbiter is not None:
            queryset = queryset.filter(Q(to_arbiter=arbiter))
        
        if rating is not None:
            queryset = queryset.filter(Q(rating=rating))

        # TODO pagination

        serializer = ArbiterFeedbackSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

    def post(self, request):

        try:
            # Validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.FEEDBACK_ARBITER_CREATE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            try:
                order = Order.objects.get(pk=request.data.get('order'))
                from_peer = Peer.objects.get(wallet_hash=wallet_hash)
                
                # Limit feedbacks to 1 per peer
                self.validate_limit(from_peer, order)
            except (Order.DoesNotExist, Peer.DoesNotExist, AssertionError) as err:
                return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate if user is allowed to feedback this order
            validate_permissions(from_peer, order)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        # TODO: block feedback if order is not yet completed

        data = request.data.copy()
        data['from_peer'] = from_peer.id
        data['to_arbiter'] = order.arbiter.id
        logger.warn(f'data: {data}')
        
        serializer = ArbiterFeedbackCreateSerializer(data=data)
        if serializer.is_valid():                        
            serializer = ArbiterFeedbackCreateSerializer(serializer.save())
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def validate_limit(self, from_peer, order):
        '''
        Limits feedback to 1 per order peer.
        '''
        feedback_count = (Feedback.objects.filter(Q(order=order) & Q(from_peer=from_peer))).count()
        assert feedback_count == 0, 'peer feedback already existing'
    
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
        data = request.data.copy()
        try:
            # validate signature
            pubkey, signature, timestamp, wallet_hash = get_verification_headers(request)

            try:
                from_peer = Peer.objects.get(wallet_hash=wallet_hash)
            except Peer.DoesNotExist:
                return Response({'error': 'no such Peer with wallet_hash'}, status=status.HTTP_400_BAD_REQUEST)
            
            data['from_peer'] = from_peer.id

            message = ViewCode.FEEDBACK_PEER_CREATE.value + '::' + timestamp
            verify_signature(wallet_hash, pubkey, signature, message)

            # validate permissions
            validate_permissions(data['from_peer'], data['order'])
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            self.validate_counterparty(
                data['from_peer'], 
                data['to_peer'], 
                data['order'])
            self.validate_limit(
                data['from_peer'], 
                data['to_peer'], 
                data['order']
            )
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
            
        serializer = FeedbackSerializer(data=data)
        if serializer.is_valid():
            
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def validate_counterparty(self, from_peer_id, to_peer_id, order_id):
        '''
        Validates if to_peer is order counterparty
        '''

        try:
            from_peer = Peer.objects.get(pk=from_peer_id)
            to_peer = Peer.objects.get(pk=to_peer_id)
            order = Order.objects.get(pk=order_id)
        except:
            raise ValidationError('peer or order does not exist')
        
        if (to_peer.wallet_hash == from_peer.wallet_hash):
            raise ValidationError('to_peer must be order counterparty')
        
        if (from_peer == order.owner and to_peer != order.ad.owner):
            raise ValidationError('to_peer must be order counterparty')
        
        if (from_peer == order.ad.owner and to_peer != order.owner):
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

def validate_permissions(from_peer, order):
    '''
    Validates if from_peer is allowed to create an arbiter feedback for this order.
    ''' 
    order_creator = order.owner.id == from_peer.id
    order_ad_creator = order.ad.owner.id == from_peer.id

    if not (order_creator or order_ad_creator):
        raise ValidationError('peer unallowed to feedback order')