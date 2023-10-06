from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from django.db.models import Q
from django.core.exceptions import ValidationError

from rampp2p.utils.signature import verify_signature, get_verification_headers
from rampp2p.models import Feedback, Peer, Order, ArbiterFeedback
from rampp2p.serializers import (
    FeedbackSerializer, 
    FeedbackCreateSerializer,
    ArbiterFeedbackSerializer, 
    ArbiterFeedbackCreateSerializer
)
from rampp2p.viewcodes import ViewCode
from authentication.token import TokenAuthentication

import logging
logger = logging.getLogger(__name__)

class ArbiterFeedbackListCreate(APIView):
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        queryset = ArbiterFeedback.objects.all()

        order_id = request.query_params.get('order_id')
        from_peer = request.query_params.get('from_peer')
        arbiter = request.query_params.get('arbiter')
        rating = request.query_params.get('rating')
        ad_id = request.query_params.get('ad_id')
        
        if ad_id is not None:
            queryset = queryset.filter(Q(order__ad_snapshot__ad_id=ad_id))
        
        if order_id is not None:
            queryset = queryset.filter(Q(order=order_id))

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

        order_id = request.data.get('order_id')
        if order_id is None:
            return Response({'error': 'order_id field may not be blank'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.FEEDBACK_ARBITER_CREATE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)
            
            # Validate if user is allowed to feedback this order
            from_peer, arbiter, order = self.validate_permissions(wallet_hash, order_id)
        except (ValidationError, Peer.DoesNotExist, Order.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            self.validate_limit(from_peer, order)
        except AssertionError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        # TODO: block feedback if order is not yet completed
        if arbiter is None:
            return Response({'error': 'order not completed yet'}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data.copy()
        data['order'] = order.id
        data['from_peer'] = from_peer.id
        data['to_arbiter'] = arbiter.id
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
        feedback_count = (ArbiterFeedback.objects.filter(Q(order=order) & Q(from_peer=from_peer))).count()
        assert feedback_count == 0, 'peer feedback already existing'
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        Validates if from_peer is allowed to create an arbiter feedback for this order.
        ''' 
        try:
            from_peer = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=pk)
        except (Peer.DoesNotExist, Order.DoesNotExist) as err:
            raise ValidationError(err.args[0])

        order_creator = order.owner.id == from_peer.id
        order_ad_creator = order.ad_snapshot.ad.owner.id == from_peer.id

        if not (order_creator or order_ad_creator):
            raise ValidationError('not allowed to feedback this order')
        
        arbiter = order.arbiter
        return from_peer, arbiter, order
    
class PeerFeedbackListCreate(APIView):
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        queryset = Feedback.objects.all()
        
        ad_id = request.query_params.get('ad_id')
        if ad_id is not None:
            queryset = queryset.filter(Q(order__ad_snapshot__ad_id=ad_id))
        
        order_id = request.query_params.get('order_id')
        if order_id is not None:
            queryset = queryset.filter(Q(order=order_id))
        
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
        
        order_id = request.data.get('order_id')
        if order_id is None:
            return Response({'error': 'order_id field may not be blank'}, status=status.HTTP_400_BAD_REQUEST)
        
            
        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.FEEDBACK_PEER_CREATE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # validate permissions
            from_peer, to_peer, order = self.validate_permissions(wallet_hash, order_id)

        except (ValidationError, Peer.DoesNotExist, Order.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            data = request.data.copy()
            data['from_peer'] = from_peer.id
            data['to_peer'] = to_peer.id
            data['order'] = order.id
            self.validate_limit(data['from_peer'], data['to_peer'], data['order'])
        except AssertionError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
            
        serializer = FeedbackCreateSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def validate_limit(self, from_peer, to_peer, order):
        '''
        Validates that from_peer can only create 1 feedback for the order.
        '''
        feedback_count = (Feedback.objects.filter(Q(from_peer=from_peer) & Q(to_peer=to_peer) & Q(order=order))).count()
        assert feedback_count == 0, 'peer feedback already existing'
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        Validates if from_peer is allowed to create a peer feedback for this order.
        ''' 
        try:
            from_peer = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=pk)
        except (Peer.DoesNotExist, Order.DoesNotExist) as err:
            raise ValidationError(err.args[0])

        order_creator = order.owner.id == from_peer.id
        order_ad_creator = order.ad_snapshot.ad.owner.id == from_peer.id

        if not (order_creator or order_ad_creator):
            raise ValidationError('not allowed to feedback this order')
        
        to_peer = None
        if order_creator:
            to_peer = order.ad_snapshot.ad.owner
        else:
            to_peer = order.owner
        
        return from_peer, to_peer, order
    
class FeedbackDetail(generics.RetrieveUpdateAPIView):
    authentication_classes = [TokenAuthentication]
    queryset = Feedback.objects.all()
    serializer_class = FeedbackSerializer

