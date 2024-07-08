from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from django.http import Http404
from django.core.exceptions import ValidationError
from authentication.token import TokenAuthentication
from django.db.models import OuterRef, Subquery
# from rampp2p.models import PaymentType, PaymentMethod, Peer, IdentifierFormat, FiatCurrency
import rampp2p.models as models
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
        queryset = models.PaymentType.objects.all()
        currency = request.query_params.get('currency')
        if currency:
            fiat_currency = models.FiatCurrency.objects.filter(symbol=currency)
            if not fiat_currency.exists():
                return Response({'error': f'no such fiat currency with symbol {currency}'}, status.HTTP_400_BAD_REQUEST)
            fiat_currency = fiat_currency.first()
            queryset = fiat_currency.payment_types
        serializer = PaymentTypeSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

class PaymentMethodListCreate(APIView):  
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        queryset = models.PaymentMethod.objects.filter(owner__wallet_hash=request.user.wallet_hash)
        currency = request.query_params.get('currency')
        if currency:
            fiat_currency = models.FiatCurrency.objects.filter(symbol=currency)
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

        format = models.IdentifierFormat.objects.filter(format=data.get('identifier_format'))
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
            payment_method = models.PaymentMethod.objects.get(pk=pk)
            return payment_method
        except models.PaymentMethod.DoesNotExist:
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
        format = models.IdentifierFormat.objects.filter(format=data.get('identifier_format'))
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
            # disable deletion if used by any Ad as payment method
            ads_using_this = models.Ad.objects.filter(deleted_at__isnull=True, payment_methods__id=payment_method.id)
            if ads_using_this.exists():
                raise ValidationError("Unable to delete Ad payment method")
    
            # disable deletion if payment method is used by ongoing orders
            latest_status_subquery = models.Status.objects.filter(
                order=OuterRef('pk'),
            ).order_by('-created_at').values('status')[:1]
            annotated_orders = models.Order.objects.annotate(latest_status = Subquery(latest_status_subquery))
            completed_status = [models.StatusType.CANCELED, models.StatusType.RELEASED, models.StatusType.REFUNDED]
            incomplete_orders = annotated_orders.exclude(latest_status__in=completed_status)
            orders_using_this = incomplete_orders.filter(payment_methods__id=payment_method.id)
            logger.warn(f'{orders_using_this.count()} orders using this payment method')
            if orders_using_this.exists():
                raise ValidationError(f"Unable to delete payment method used by {orders_using_this.count()} ongoing order(s)")
            
            payment_method.delete()
        except Exception as err:
            return Response({'error': err.args[0]},status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_200_OK)

    def validate_permissions(self, wallet_hash, id):
        '''
        Validates if caller is owner
        '''
        try:
            payment_method = models.PaymentMethod.objects.get(pk=id)
            caller = models.Peer.objects.get(wallet_hash=wallet_hash)
        except (models.PaymentMethod.DoesNotExist, models.Peer.DoesNotExist) as err:
            raise ValidationError(err.args[0])
        
        if caller.wallet_hash != payment_method.owner.wallet_hash:
            raise ValidationError('caller must be payment method owner')