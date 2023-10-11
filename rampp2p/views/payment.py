from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.http import Http404
from django.core.exceptions import ValidationError

from rampp2p.models import PaymentType, PaymentMethod, Peer
from rampp2p.utils.signature import verify_signature, get_verification_headers
from rampp2p.serializers import (
    PaymentMethodCreateSerializer,
    PaymentTypeSerializer, 
    PaymentMethodSerializer,
    PaymentMethodUpdateSerializer
)
from rampp2p.viewcodes import ViewCode
from authentication.token import TokenAuthentication

import logging
logger = logging.getLogger(__name__)

class PaymentTypeList(APIView):
    authentication_classes = [TokenAuthentication]

    def get(self, _):
        queryset = PaymentType.objects.all()
        serializer = PaymentTypeSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

class PaymentMethodListCreate(APIView):  
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        queryset = PaymentMethod.objects.filter(owner=request.user)
        serializer = PaymentMethodSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

    def post(self, request):
        data = request.data.copy()
        data['owner'] = request.user.id

        serializer = PaymentMethodCreateSerializer(data=data)
        if serializer.is_valid():
            payment_method = serializer.save()
            serializer = PaymentMethodSerializer(payment_method)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
  
class PaymentMethodDetail(APIView):
    authentication_classes = [TokenAuthentication]
    
    def get_object(self, pk):
        try:
            payment_method = PaymentMethod.objects.get(pk=pk)
            return payment_method
        except PaymentMethod.DoesNotExist:
            raise Http404
    
    def get(self, request, pk):
        try:
            self.validate_permissions(request.user.wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        payment_method = self.get_object(pk)
        serializer = PaymentMethodSerializer(payment_method)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        try:
            self.validate_permissions(request.user.wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        payment_method = self.get_object(pk=pk)
        serializer = PaymentMethodUpdateSerializer(payment_method, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        try:
            self.validate_permissions(request.user.wallet_hash, pk)
            payment_method = self.get_object(pk=pk)
            payment_method.delete()
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        except Exception as err:
            return Response({'error': err.args[0]},status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_200_OK)

    def validate_permissions(self, wallet_hash, id):
        '''
        Validates if caller is owner
        '''
        try:
            payment_method = PaymentMethod.objects.get(pk=id)
            caller = Peer.objects.get(wallet_hash=wallet_hash)
        except (PaymentMethod.DoesNotExist, Peer.DoesNotExist) as err:
            raise ValidationError(err.args[0])
        
        if caller.wallet_hash != payment_method.owner.wallet_hash:
            raise ValidationError('caller must be payment method owner')