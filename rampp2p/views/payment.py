from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.http import Http404
from django.core.exceptions import ValidationError

from rampp2p.models import PaymentType, PaymentMethod, Peer
from rampp2p.utils.signature import verify_signature, get_verification_headers
from rampp2p.serializers import PaymentTypeSerializer, PaymentMethodSerializer
from rampp2p.viewcodes import ViewCode

class PaymentTypeList(APIView):
    def get(self, request):
        queryset = PaymentType.objects.all()
        serializer = PaymentTypeSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

class PaymentTypeDetail(APIView):
    def get_object(self, pk):
        try:
            return PaymentType.objects.get(pk=pk)
        except PaymentType.DoesNotExist:
            raise Http404

    def get(self, request, pk):
        payment_type = self.get_object(pk)
        serializer = PaymentTypeSerializer(payment_type)
        return Response(serializer.data, status=status.HTTP_200_OK)

class PaymentMethodListCreate(APIView):
    
    def get(self, request):
        
        try:
            pubkey, signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.LIST_PAYMENT_METHOD.value + '::' + timestamp
            verify_signature(wallet_hash, pubkey, signature, message)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
           owner = Peer.objects.get(wallet_hash=wallet_hash)
        except Peer.DoesNotExist:
           return Response({'error': 'no such Peer with wallet_hash'}, status=status.HTTP_400_BAD_REQUEST)
            
        queryset = PaymentMethod.objects.filter(owner=owner, is_deleted=False)
        serializer = PaymentMethodSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

    def post(self, request):

        try:
            pubkey, signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.POST_PAYMENT_METHOD.value + '::' + timestamp
            verify_signature(wallet_hash, pubkey, signature, message)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
           owner = Peer.objects.get(wallet_hash=wallet_hash)
        except Peer.DoesNotExist:
           return Response({'error': 'no such Peer with wallet_hash'}, status=status.HTTP_400_BAD_REQUEST)
        
        data = request.data.copy()
        data['owner'] = owner.id

        serializer = PaymentMethodSerializer(data=data)
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
            pubkey, signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.GET_PAYMENT_METHOD.value + '::' + timestamp
            verify_signature(wallet_hash, pubkey, signature, message)
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        payment_method = self.get_object(pk)
        serializer = PaymentMethodSerializer(payment_method)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        try:
            pubkey, signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.PUT_PAYMENT_METHOD.value + '::' + timestamp
            verify_signature(wallet_hash, pubkey, signature, message)
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        try:
           owner = Peer.objects.get(wallet_hash=wallet_hash)
        except Peer.DoesNotExist:
           return Response({'error': 'no such Peer with wallet_hash'}, status=status.HTTP_400_BAD_REQUEST)
        
        payment_method = self.get_object(pk=pk)
        account_name = request.data.get('account_name', None)
        account_number = request.data.get('account_number', None)

        if account_name is not None:
           payment_method.account_name = account_name

        if account_number is not None:
           payment_method.account_number = account_number
        
        payment_method.owner = owner
        payment_method.save()
        serializer = PaymentMethodSerializer(payment_method)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        try:
            pubkey, signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.DEL_PAYMENT_METHOD.value + '::' + timestamp
            verify_signature(wallet_hash, pubkey, signature, message)
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        payment_method = self.get_object(pk=pk)
        if not payment_method.is_deleted:
            payment_method.is_deleted = True
            payment_method.deleted_at = timezone.now()
            payment_method.save()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def validate_permissions(self, wallet_hash, id):
        '''
        Validates if caller is owner
        '''

        try:
            payment_method = PaymentMethod.objects.get(pk=id)
            caller = Peer.objects.get(wallet_hash=wallet_hash)
        except PaymentMethod.DoesNotExist or Peer.DoesNotExist:
            raise ValidationError('payment method or peer does not exist')
        
        if caller.wallet_hash != payment_method.owner.wallet_hash:
            raise ValidationError('caller must be ad owner')