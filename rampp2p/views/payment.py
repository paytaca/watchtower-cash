from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from django.http import Http404
from django.core.exceptions import ValidationError
from authentication.token import TokenAuthentication
from django.db.models import OuterRef, Subquery, Q
import rampp2p.models as models
import rampp2p.serializers as serializers

import logging
logger = logging.getLogger(__name__)

class PaymentTypeList(APIView):
    swagger_schema = None
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
        serializer = serializers.PaymentTypeSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

class PaymentMethodListCreate(APIView): 
    swagger_schema = None 
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
        serializer = serializers.PaymentMethodSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

    def post(self, request):
        data = request.data.copy()
        owner = request.user
        logger.warn(f'request data: {data}')
        try:
            payment_type = models.PaymentType.objects.get(id=data.get('payment_type'))
            logger.warn(f'payment_type: {payment_type}')
            # Return an error if a payment_method with same payment type already exists for this user
            if models.PaymentMethod.objects.filter(Q(owner__wallet_hash=owner.wallet_hash) & Q(payment_type__id=payment_type.id)).exists():
                return Response({'error': 'Duplicate payment method with payment type'}, status=status.HTTP_400_BAD_REQUEST)

            data = {
                'payment_type': payment_type.id,
                'owner': owner.id
            }
        except models.PaymentType.DoesNotExist as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        logger.warn(f'data: {data}')
        serializer = serializers.PaymentMethodSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        payment_method = serializer.save()
        serializer = serializers.PaymentMethodSerializer(payment_method)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
  
class PaymentMethodDetail(APIView):
    swagger_schema = None
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
        serializer = serializers.PaymentMethodSerializer(payment_method)
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
        serializer = serializers.PaymentMethodUpdateSerializer(payment_method, data=data)
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