from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone
from django.http import Http404
from django.core.exceptions import ValidationError
from typing import List

from rampp2p.viewcodes import ViewCode
from rampp2p.utils.signature import verify_signature, get_verification_headers
from rampp2p.serializers import (
    AdListSerializer, 
    AdDetailSerializer,
    AdCreateSerializer, 
    AdUpdateSerializer
)
from rampp2p.models import Ad, Peer, PaymentMethod

class AdListCreate(APIView):
    def get(self, request):
        queryset = Ad.objects.filter(is_deleted=False)

        # TODO pagination

        wallet_hash = request.headers.get('wallet_hash')
        currency = request.query_params.get('currency')

        if wallet_hash is not None:
            try:
                # Verify owner signature
                signature, timestamp, _ = get_verification_headers(request)
                message = ViewCode.AD_LIST.value + '::' + timestamp
                verify_signature(wallet_hash, signature, message)
            except ValidationError as err:
                return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

            queryset = queryset.filter(Q(owner__wallet_hash=wallet_hash))

        if currency is not None:
            queryset = queryset.filter(Q(fiat_currency__symbol=currency))
        
        serializer = AdListSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

    def post(self, request):
        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.AD_CREATE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # Validate that user owns the payment methods
            payment_methods = request.data.get('payment_methods')
            validate_payment_methods_ownership(wallet_hash, payment_methods)

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
    
        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
        except Peer.DoesNotExist as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        data = request.data.copy()
        data['owner'] = caller.id

        serializer = AdCreateSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AdDetail(APIView):
    def get_object(self, pk):
        try:
            return Ad.objects.get(pk=pk)
        except Ad.DoesNotExist:
            raise Http404

    def get(self, _, pk):
        ad = self.get_object(pk)
        if ad.is_deleted:
            return Response(status=status.HTTP_204_NO_CONTENT)
        serializer = AdDetailSerializer(ad)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):

        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.AD_UPDATE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)
            
            # Validate that user owns the payment methods
            payment_methods = request.data.get('payment_methods')
            validate_payment_methods_ownership(wallet_hash, payment_methods)

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        ad = self.get_object(pk)
        serializer = AdUpdateSerializer(ad, data=request.data)
        if serializer.is_valid():
            ad = serializer.save()
            serializer = AdListSerializer(ad)
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk):
        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.AD_DELETE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        # TODO: block deletion when ad has active orders
        
        ad = self.get_object(pk)
        if not ad.is_deleted:
            ad.is_deleted = True
            ad.deleted_at = timezone.now()
            ad.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    def validate_permissions(self, wallet_hash, ad_id):
        '''
        Validates if caller is ad owner
        '''
        try:
            ad = Ad.objects.get(pk=ad_id)
            caller = Peer.objects.get(wallet_hash=wallet_hash)
        except (Ad.DoesNotExist, Peer.DoesNotExist) as err:
            raise ValidationError(err.args[0])
        
        if caller.wallet_hash != ad.owner.wallet_hash:
            raise ValidationError('caller must be ad owner')
    
def validate_payment_methods_ownership(wallet_hash, payment_method_ids):
    '''
    Validates if caller owns the payment methods
    '''
    if payment_method_ids is None:
        raise ValidationError('payment_methods field is required')
    
    try:
        caller = Peer.objects.get(wallet_hash=wallet_hash)
    except Peer.DoesNotExist as err:
        raise ValidationError(err.args[0])

    payment_methods = PaymentMethod.objects.filter(Q(id__in=payment_method_ids))
    for payment_method in payment_methods:
        if payment_method.owner.wallet_hash != caller.wallet_hash:
            raise ValidationError('caller must be owner of payment method')