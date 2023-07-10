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

class PaymentTypeList(APIView):
    def get(self, _):
        queryset = PaymentType.objects.all()
        serializer = PaymentTypeSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

class PaymentMethodListCreate(APIView):   
    def get(self, request):
        try:
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.PAYMENT_METHOD_LIST.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
           owner = Peer.objects.get(wallet_hash=wallet_hash)
        except Peer.DoesNotExist as err:
           return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
            
        queryset = PaymentMethod.objects.filter(owner=owner, is_deleted=False)
        serializer = PaymentMethodSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

    def post(self, request):

        try:
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.PAYMENT_METHOD_CREATE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
           owner = Peer.objects.get(wallet_hash=wallet_hash)
        except Peer.DoesNotExist as err:
           return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        data = request.data.copy()
        data['owner'] = owner.id

        serializer = PaymentMethodCreateSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
  
class PaymentMethodDetail(APIView):
    def get_object(self, pk):
        try:
            queryset = PaymentMethod.objects.filter(is_deleted=False) 
            return queryset.get(pk=pk)
        except PaymentMethod.DoesNotExist:
            raise Http404
    
    def get(self, request, pk):
        try:
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.PAYMENT_METHOD_GET.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # Validate that caller is payment method owner
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        payment_method = self.get_object(pk)
        serializer = PaymentMethodSerializer(payment_method)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        try:
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.PAYMENT_METHOD_UPDATE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # Validate that caller is payment method owner
            self.validate_permissions(wallet_hash, pk)
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
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.PAYMENT_METHOD_DELETE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # Validate that caller is payment method owner
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        payment_method = self.get_object(pk=pk)
        if not payment_method.is_deleted:
            payment_method.is_deleted = True
            payment_method.deleted_at = timezone.now()
            payment_method.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

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