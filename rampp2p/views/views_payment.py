from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets

from django.db import transaction
from django.http import Http404
from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Subquery, Q

from authentication.token import TokenAuthentication
from authentication.permissions import RampP2PIsAuthenticated

import rampp2p.models as models
import rampp2p.serializers as serializers

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
        serializer = serializers.PaymentTypeSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

class PaymentMethodViewSet(viewsets.GenericViewSet):  
    authentication_classes = [TokenAuthentication]
    permission_classes = [RampP2PIsAuthenticated]
    queryset = models.PaymentMethod.objects.all()

    def list(self, request):
        queryset = self.get_queryset().filter(owner__wallet_hash=request.user.wallet_hash)
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

    def create(self, request):
        owner = request.user
        
        try:
            data = request.data.copy()
            fields = data.get('fields')
            if fields is None or len(fields) == 0:
                raise ValidationError('Empty payment method fields')
            
            payment_type = models.PaymentType.objects.get(id=data.get('payment_type'))

            # Return error if a payment_method with same payment type already exists for this user
            if models.PaymentMethod.objects.filter(Q(owner__wallet_hash=owner.wallet_hash) & Q(payment_type__id=payment_type.id)).exists():
                raise ValidationError('Duplicate payment method with payment type')

            data = {
                'payment_type': payment_type,
                'owner': owner
            }        

            with transaction.atomic():
                # create payment method
                payment_method = models.PaymentMethod.objects.create(**data)
                # create payment method fields
                for field in fields:
                    field_ref = models.PaymentTypeField.objects.get(id=field['field_reference'])
                    data = {
                        'payment_method': payment_method,
                        'field_reference': field_ref,
                        'value': field['value']
                    }
                    models.PaymentMethodField.objects.create(**data)
                
            serializer = serializers.PaymentMethodSerializer(payment_method)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
    
    def retrieve(self, request, pk):
        try:
            payment_method = self.get_queryset().get(pk=pk)
            self._check_permissions(request.user.wallet_hash, payment_method)
            serializer = serializers.PaymentMethodSerializer(payment_method)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, pk):
        try:
            payment_method = self.get_queryset().get(pk=pk)
            self._check_permissions(request.user.wallet_hash, payment_method)
        
            data = request.data.copy()
            fields = data.get('fields')
            if fields is None or len(fields) == 0:
                raise ValidationError('Empty payment method fields')

            for field in data.get('fields'):
                field_id = field.get('id')
                if field_id:
                    payment_method_field = models.PaymentMethodField.objects.get(id=field_id)
                    payment_method_field.value = field.get('value')
                    payment_method_field.save()
                elif field.get('value') and field.get('field_reference'):
                    field_ref = models.PaymentTypeField.objects.get(id=field.get('field_reference'))
                    data = {
                        'payment_method': payment_method,
                        'field_reference': field_ref,
                        'value': field.get('value')
                    }
                    models.PaymentMethodField.objects.create(**data)

            serializer = serializers.PaymentMethodSerializer(payment_method)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
    def destroy(self, request, pk):
        try:
            payment_method = self.get_queryset().get(pk=pk)
            self._check_permissions(request.user.wallet_hash, payment_method)
            
            # disable deletion if used by any Ad as payment method
            ads_using_this = models.Ad.objects.filter(deleted_at__isnull=True, payment_methods__id=payment_method.id)
            if ads_using_this.exists():
                raise ValidationError("Unable to delete Ad payment method")
    
            # disable deletion if payment method is used by ongoing orders
            latest_status_subquery = models.Status.objects.filter(order=OuterRef('pk')).order_by('-created_at').values('status')[:1]
            annotated_orders = models.Order.objects.annotate(latest_status = Subquery(latest_status_subquery))
            completed_status = [models.StatusType.CANCELED, models.StatusType.RELEASED, models.StatusType.REFUNDED]
            incomplete_orders = annotated_orders.exclude(latest_status__in=completed_status)
            orders_using_this = incomplete_orders.filter(payment_methods__id=payment_method.id)
            logger.warning(f'{orders_using_this.count()} orders using this payment method')
            if orders_using_this.exists():
                raise ValidationError(f"Unable to delete payment method used by {orders_using_this.count()} ongoing order(s)")
            
            payment_method.delete()
            return Response(status=status.HTTP_200_OK)
        except Exception as err:
            return Response({'error': err.args[0]},status=status.HTTP_400_BAD_REQUEST)

    def _check_permissions(self, wallet_hash, payment_method):
        '''Throws an error if wallet_hash is not the owner of payment_method.'''        
        if wallet_hash != payment_method.owner.wallet_hash:
            raise ValidationError('User not allowed to access this payment method.')