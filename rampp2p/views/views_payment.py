from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.parsers import MultiPartParser
from rest_framework.decorators import action

from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Subquery, Q
from django.utils.translation import gettext_lazy as _

from authentication.token import TokenAuthentication
from authentication.permissions import RampP2PIsAuthenticated

import rampp2p.models as models
import rampp2p.serializers as serializers
import rampp2p.utils.file_upload as file_upload_utils
import rampp2p.utils.utils as rampp2putils

from PIL import Image

import logging
logger = logging.getLogger(__name__)

class PaymentTypeView(APIView):
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        queryset = models.PaymentType.objects.filter(payment_currency__isnull=False)
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
        
class OrderPaymentViewSet(viewsets.GenericViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [RampP2PIsAuthenticated]
    parser_classes = [MultiPartParser]
    queryset = models.OrderPayment.objects.all()

    def list(self, request):
        queryset = self.get_queryset()
        order_id = request.query_params.get('order_id')
        if order_id:
            queryset = queryset.filter(order__id=order_id)
        serializer = serializers.OrderPaymentSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def retrieve(self, request, pk):
        try: 
            queryset = self.get_queryset().get(pk=pk)
            serializer = serializers.OrderPaymentSerializer(queryset)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except models.OrderPayment.DoesNotExist as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def upload_attachment(self, request, pk):
        try:
            image_file = request.FILES.get('image')
            if image_file is None: raise ValidationError('image is required')
            order_payment_obj = models.OrderPayment.objects.prefetch_related('order').get(id=pk)

            # Order status must be ESCROWED or PAID PENDING for payment attachment upload.
            self._validate_awaiting_payment(order_payment_obj.order)

            filesize = image_file.size
            if filesize > 5 * 1024 * 1024: # 5mb limit
                raise ValidationError(
                    { 'image': _('File size cannot exceed 5 MB.')}
                )

            img_object = Image.open(image_file)
            image_upload_obj = file_upload_utils.save_image(img_object, max_width=450, request=request)

            attachment, _ = models.OrderPaymentAttachment.objects.update_or_create(payment=order_payment_obj, image=image_upload_obj)
            serializer = serializers.OrderPaymentAttachmentSerializer(attachment)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        except (models.OrderPayment.DoesNotExist, ValidationError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
    @action(detail=True, methods=['delete'])
    def delete_attachment(self, request, pk):
        try:
            attachment = models.OrderPaymentAttachment.objects.get(id=pk)
            self._validate_awaiting_payment(attachment.payment.order)
            file_upload_utils.delete_file(attachment.image.url_path)
            attachment.delete()
            return Response(status=status.HTTP_200_OK)
        
        except (models.OrderPaymentAttachment.DoesNotExist, Exception) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    def _validate_awaiting_payment(self, order):
        '''Validates that `order` is awaiting fiat payment. Raises ValidationError 
        when order's last status is not ESCRW nor PD_PN'''
        last_status = rampp2putils.get_last_status(order.id)
        if last_status.status != models.StatusType.ESCROWED and last_status.status != models.StatusType.PAID_PENDING:
            raise ValidationError({ 'order': _(f'Invalid action for {last_status.status} order')})
