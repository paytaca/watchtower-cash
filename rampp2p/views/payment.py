from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from django.http import Http404
from django.core.exceptions import ValidationError

from authentication.token import TokenAuthentication

from rampp2p.models import PaymentType, PaymentMethod, Peer, IdentifierFormat, FiatCurrency
from rampp2p.serializers import (
    PaymentTypeSerializer, 
    PaymentMethodSerializer,
    PaymentMethodCreateSerializer,
    PaymentMethodUpdateSerializer
)

import logging
logger = logging.getLogger(__name__)

class PaymentTypeList(APIView):
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        queryset = PaymentType.objects.all()
        currency = request.query_params.get('currency')
        if currency:
            fiat_currency = FiatCurrency.objects.filter(symbol=currency)
            if not fiat_currency.exists():
                return Response({'error': f'no such fiat currency with symbol {currency}'}, status.HTTP_400_BAD_REQUEST)
            fiat_currency = fiat_currency.first()
            queryset = fiat_currency.payment_types
        serializer = PaymentTypeSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

class PaymentMethodListCreate(APIView):  
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        queryset = PaymentMethod.objects.filter(owner__wallet_hash=request.user.wallet_hash)
        currency = request.query_params.get('currency')
        if currency:
            fiat_currency = FiatCurrency.objects.filter(symbol=currency)
            if not fiat_currency.exists():
                return Response({'error': f'no such fiat currency with symbol {currency}'}, status.HTTP_400_BAD_REQUEST)
            fiat_currency = fiat_currency.first()
            currency_paymenttype_ids = fiat_currency.payment_types.values_list('id', flat=True)
            queryset = queryset.filter(payment_type__id__in=currency_paymenttype_ids)
        serializer = PaymentMethodSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

    def post(self, request):
        data = request.data.copy()
        data['owner'] = request.user.id

        format = IdentifierFormat.objects.filter(format=data.get('identifier_format'))
        if not format.exists():
            return Response({'error': 'identifier_format is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        data['identifier_format'] = format.first().id
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
        
        data = request.data.copy()
        format = IdentifierFormat.objects.filter(format=data.get('identifier_format'))
        if not format.exists():
            return Response({'error': 'identifier_format is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        data['identifier_format'] = format.first().id
        payment_method = self.get_object(pk=pk)
        serializer = PaymentMethodUpdateSerializer(payment_method, data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        try:
            self.validate_permissions(request.user.wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            payment_method = self.get_object(pk=pk)
            payment_method.delete()
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