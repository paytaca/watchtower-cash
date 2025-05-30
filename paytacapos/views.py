from django.db.models import (
    F, Value,
    Func,
    ExpressionWrapper,
    CharField,
    Max,
)
from django.http import Http404
from django.db import transaction
from django.utils import timezone
from django_filters import rest_framework as filters
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets, mixins, decorators, exceptions, permissions
from rest_framework import status
from rest_framework.exceptions import MethodNotAllowed

from .serializers import *
from .filters import *
from .permissions import HasMerchantObjectPermission, HasMinPaytacaVersionHeader, HasPaymentObjectPermission
from .pagination import CustomLimitOffsetPagination
from .utils.websocket import send_device_update
from .utils.report import SalesSummary
from .utils.cash_out import fetch_unspent_merchant_transactions, generate_payout_address

from .models import Location, Category, Merchant, PosDevice, CashOutPaymentMethod
from main.models import Address, Transaction, WalletHistory
from rampp2p.models import MarketPrice
from .tasks import process_cashout_input_txns

from authentication.token import WalletAuthentication
from django.core.exceptions import ValidationError

import math
import logging

logger = logging.getLogger(__name__)


class BroadcastPaymentView(APIView):
    @swagger_auto_schema(
        request_body=POSPaymentSerializer,
        responses={200: POSPaymentResponseSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = POSPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer_save_data = serializer.save()
        success_data = POSPaymentResponseSerializer(serializer_save_data).data
        return Response(success_data, status=status.HTTP_200_OK)


class PosDeviceViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
):
    serializer_class = PosDeviceSerializer
    # lookup field is an annotated string with pattern '{wallet_hash}:{posid}'
    lookup_field = "wallet_hash_posid"
    pagination_class = CustomLimitOffsetPagination

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = PosDeviceFilter

    permission_classes = [
        HasMinPaytacaVersionHeader | HasMerchantObjectPermission,
    ]

    authentication_classes = [
        WalletAuthentication,
    ]

    def get_queryset(self):
        return self.serializer_class.Meta.model.objects.annotate(
            wallet_hash_posid=ExpressionWrapper(
                Func(F("wallet_hash"), Value(":"), F("posid"), function="CONCAT"),
                output_field=CharField(max_length=75),
            )
        ).all()

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.linked_device:
            return Response(["POS device is linked, unlink device first"], status=400)

        response = super().destroy(request, *args, **kwargs)
        send_device_update(instance, action="destroy")
        return response

    @swagger_auto_schema(method="post", request_body=SuspendDeviceSerializer, responses={ 200: serializer_class })
    @decorators.action(methods=["post"], detail=True)
    def suspend(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = SuspendDeviceSerializer(pos_device=instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(self.get_serializer(instance).data)

    @swagger_auto_schema(method="post", request_body=LatestPosIdSerializer, response={ 200: { 'posid': 0 } })
    @decorators.action(methods=['post'], detail=False)
    def latest_posid(self, request, *args, **kwargs):
        serializer = LatestPosIdSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({ 'posid': 0 })

    @transaction.atomic
    @swagger_auto_schema(method="post", request_body=UnlinkDeviceSerializer, responses={ 200: serializer_class })
    @decorators.action(methods=["post"], detail=True)
    def unlink_device(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = UnlinkDeviceSerializer(pos_device=instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(self.get_serializer(instance).data)

    @transaction.atomic
    @swagger_auto_schema(method="post", request_body=UnlinkDeviceRequestSerializer, responses={ 200: serializer_class })
    @decorators.action(methods=["post"], detail=True, url_path=f"unlink_device/request")
    def unlink_device_request(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = UnlinkDeviceRequestSerializer(linked_device_info=instance.linked_device, data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        pos_device_instance = instance.linked_device_info.pos_device
        send_device_update(pos_device_instance, action="unlink_request")
        return Response(self.get_serializer(pos_device_instance).data)

    @swagger_auto_schema(method="post", request_body=openapi.Schema(type=openapi.TYPE_OBJECT), responses={ 200: serializer_class })
    @decorators.action(methods=["post"], detail=True, url_path=f"unlink_device/cancel")
    def cancel_unlink_request(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.linked_device and instance.linked_device.get_unlink_request():
            instance.linked_device.get_unlink_request().delete()
            instance.refresh_from_db()
        return Response(self.get_serializer(instance).data)

    @swagger_auto_schema(method="post", request_body=PosDeviceLinkRequestSerializer, responses={ 200: PosDeviceLinkSerializer })
    @decorators.action(methods=["post"], detail=False)
    def generate_link_device_code(self, request, *args, **kwargs):
        serializer = PosDeviceLinkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.save_link_request()
        return Response(data)

    @swagger_auto_schema(
        method="get",
        responses={ 200: openapi.Schema(type=openapi.TYPE_STRING) },
        manual_parameters=[
            openapi.Parameter(name="code", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY),
        ]
    )
    @decorators.action(methods=["get"], detail=False)
    def link_code_data(self, request, *args, **kwargs):
        link_code = request.query_params.get("code", None)
        link_request_data = PosDeviceLinkRequestSerializer.retrieve_link_request_data(link_code)
        code_ttl = 60 * 5
        serializer = PosDeviceLinkRequestSerializer(data=link_request_data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        return Response(serializer.validated_data["encrypted_xpubkey"])

    @swagger_auto_schema(method="post", request_body=LinkedDeviceInfoSerializer)
    @decorators.action(methods=["post"], detail=False)
    def redeem_link_device_code(self, request, *args, **kwargs):
        serializer = LinkedDeviceInfoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        serializer.remove_link_code_data()
        send_device_update(instance.pos_device, action="link")
        return Response(self.serializer_class(instance.pos_device).data)

    @swagger_auto_schema(
        method="get",
        responses={ 200: SalesSummarySerializer(many=True) },
        manual_parameters=[
            openapi.Parameter(name="range", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, default="month", enum=["month", "day"]),
            openapi.Parameter(name="posid", type=openapi.TYPE_NUMBER, in_=openapi.IN_QUERY, required=False),
            openapi.Parameter(name="from", type=openapi.TYPE_NUMBER, in_=openapi.IN_QUERY, required=False),
            openapi.Parameter(name="to", type=openapi.TYPE_NUMBER, in_=openapi.IN_QUERY, required=False),
            openapi.Parameter(name="currency", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, required=False),
        ]
    )
    @decorators.action(
        methods=["get"],
        detail=False,
        pagination_class=None,
        filter_backends=[],
        url_path=f"sales_report/(?P<wallet_hash>[^/.]+)",
    )
    def sales_report(self, request, *args, **kwargs):
        wallet_hash = kwargs["wallet_hash"]
        currency = request.query_params.get("currency", None)
        summary_range = request.query_params.get("range", "month")
        posid = request.query_params.get("posid", None)
        try:
            posid = int(posid)
        except (TypeError, ValueError):
            posid = None

        try:
            timestamp_from = int(request.query_params.get("from", None))
            timestamp_from = timezone.datetime.fromtimestamp(timestamp_from).replace(tzinfo=timezone.pytz.UTC)
        except (TypeError, ValueError):
            timestamp_from = None

        try:
            timestamp_to = int(request.query_params.get("to", None))
            timestamp_to = timezone.datetime.fromtimestamp(timestamp_to).replace(tzinfo=timezone.pytz.UTC)
        except (TypeError, ValueError):
            timestamp_to = None

        sales_summary = SalesSummary.get_summary(
            wallet_hash=wallet_hash, posid=posid,
            summary_range=summary_range,
            timestamp_from=timestamp_from, timestamp_to=timestamp_to,
            currency=currency,
        )

        serializer = SalesSummarySerializer(sales_summary)
        return Response(serializer.data)


class MerchantViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "head", "patch", "delete"]

    # lookup_field="wallet_hash"
    pagination_class = CustomLimitOffsetPagination
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = MerchantFilter

    permission_classes = [
        HasMinPaytacaVersionHeader | HasMerchantObjectPermission,
    ]
    authentication_classes = [
        WalletAuthentication,
    ]

    def get_object(self, *args, **kwargs):
        lookup_value = self.kwargs.get(self.lookup_field)
        try:
            int(lookup_value)
            return super().get_object(*args, **kwargs)
        except (TypeError, ValueError):
            pass

        try:
            return Merchant.objects.get(wallet_hash=lookup_value)
        except Merchant.DoesNotExist:
            raise Http404
        except Merchant.MultipleObjectsReturned:
            raise exceptions.APIException("Found multiple merchant with provided wallet_hash")

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(name="has_pagination", type=openapi.TYPE_BOOLEAN, in_=openapi.IN_QUERY, required=False),
        ]
    )
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        has_pagination = self.request.query_params.get('has_pagination', 'true')
        has_pagination = has_pagination.lower() == 'true'

        if page is not None and has_pagination:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.devices.count():
            raise exceptions.ValidationError("Unable to remove merchant linked to a device")
        return super().destroy(request, *args, **kwargs)
    
    @swagger_auto_schema(request_body=WalletLatestMerchantIndexSerializer, response={ 200: WalletLatestMerchantIndexResponseSerializer })
    @decorators.action(methods=['post'], detail=False)
    def latest_index(self, request, *args, **kwargs):
        serializer = WalletLatestMerchantIndexSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        index = Merchant.get_latest_merchant_index(**serializer.validated_data)
        response = { 'index': index }
        return Response(response)

    @swagger_auto_schema(method="post", request_body=MerchantVaultAddressSerializer, response={ 200: MerchantListSerializer })
    @decorators.action(methods=["post"], detail=False)
    def vault_address(self, request, *args, **kwargs):
        serializer = MerchantVaultAddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        address = Address.objects.get(address=serializer.validated_data['address'])
        try:
            pos_device = PosDevice.objects.get(
                wallet_hash=address.wallet.wallet_hash,
                posid=serializer.validated_data['posid']
            )
        except:
            return Response({})

        serializer = MerchantListSerializer(pos_device.merchant)
        return Response(serializer.data)

    @decorators.action(methods=['get'], detail=False)
    def countries(self, request, *args, **kwargs):
        locations = Location.objects.filter(
            country__isnull=False,
            merchant__isnull=False,
            merchant__active=True,
            merchant__verified=True
        ).exclude(
            country=""
        )
        locations = locations.values('country').distinct()
        locations = locations.values_list('country', flat=True)
        return Response(list(locations))

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(name="country", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, required=False),
        ]
    )
    @decorators.action(methods=['get'], detail=False)
    def cities(self, request, *args, **kwargs):
        country = request.query_params.get('country', None)
        locations = Location.objects.filter(
            country__isnull=False,
            city__isnull=False,
            merchant__isnull=False,
            merchant__active=True,
            merchant__verified=True
        ).exclude(
            city=""
        )

        if country:
            locations = locations.filter(country__icontains=country)

        cities = locations.values('city').distinct()
        cities = cities.values_list('city', flat=True)
        return Response(list(cities))

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(name="country", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, required=False),
            openapi.Parameter(name="city", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, required=False),
        ]
    )
    @decorators.action(methods=['get'], detail=False)
    def streets(self, request, *args, **kwargs):
        country = request.query_params.get('country', None)
        city = request.query_params.get('city', None)
        locations = Location.objects.filter(
            country__isnull=False,
            city__isnull=False,
            street__isnull=False,
            merchant__isnull=False,
            merchant__active=True,
            merchant__verified=True
        ).exclude(
            street=""
        )

        if country:
            locations = locations.filter(country__icontains=country)
        if city:
            locations = locations.filter(city__icontains=city)

        streets = locations.values('street').distinct()
        streets = streets.values_list('street', flat=True)
        return Response(list(streets))

    @decorators.action(methods=['get'], detail=False)
    def categories(self, request, *args, **kwargs):
        categories = Category.objects.values_list('name', flat=True)
        return Response(list(categories))

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(name="merchant", type=openapi.TYPE_NUMBER, in_=openapi.IN_QUERY, required=False),
        ]
    )
    @decorators.action(methods=['get'], detail=False)
    def reviews(self, request, *args, **kwargs):
        merchant_id = self.request.query_params.get('merchant', None)
        reviews = Review.objects.all()

        if merchant_id:
            merchant = Merchant.objects.get(id=merchant_id)
            reviews = merchant.reviews.all()

        page = self.paginate_queryset(reviews)
        if page is not None:
            serializer = ReviewSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ReviewSerializer(reviews, many=True)
        return Response(serializer.data)
    
    def get_serializer_class(self):
        if self.action in ['list']:
            return MerchantListSerializer
        else:
            return MerchantSerializer

    def get_queryset(self):
        serializer = self.get_serializer_class()
        queryset = serializer.Meta.model.objects\
            .annotate_branch_count()\
            .annotate_pos_device_count()\
            .prefetch_related('location')\
            .all()

        return queryset


class BranchViewSet(viewsets.ModelViewSet):
    serializer_class = BranchSerializer
    pagination_class = CustomLimitOffsetPagination

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = BranchFilter

    permission_classes = [
        HasMinPaytacaVersionHeader | HasMerchantObjectPermission,
    ]

    authentication_classes = [
        WalletAuthentication,
    ]

    def get_queryset(self):
        return self.serializer_class.Meta.model.objects.all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.devices.count():
            raise exceptions.ValidationError("Unable to remove branches linked to a device")
        return super().destroy(request, *args, **kwargs)

class CashOutViewSet(viewsets.ModelViewSet):
    queryset = CashOutOrder.objects.all()
    serializer_class = CashOutOrderSerializer
    authentication_classes = [WalletAuthentication]

    def get_queryset(self):
        return self.queryset.order_by('-created_at')

    def list(self, request, *args, **kwargs):
        try:
            wallet = request.user
            limit = int(request.query_params.get('limit', 0))
            page = int(request.query_params.get('page', 1))
            merchant_ids = request.query_params.getlist('merchant_ids', [])
            order_types = request.query_params.getlist('order_types', [])

            if limit < 0:
                raise ValidationError('limit must be a non-negative number')
            
            if page < 1:
                raise ValidationError('invalid page number')

            queryset = self.get_queryset()
            queryset = queryset.filter(wallet__wallet_hash=wallet.wallet_hash)

            if len(merchant_ids) > 0:
                queryset = queryset.filter(merchant__id__in=merchant_ids)

            if len(order_types) > 0:
                queryset = queryset.filter(status__in=order_types)
            
            queryset = queryset.order_by('-created_at')
            count = queryset.count()
            total_pages = page
            if limit > 0:
                total_pages = math.ceil(count / limit)

            offset = (page - 1) * limit
            paged_queryset = queryset[offset:offset + limit]

            serializer = self.get_serializer(paged_queryset, many=True)
            data = {
                'orders': serializer.data,
                'count': count,
                'total_pages': total_pages
            }
            return Response(data)
        except ValidationError as err:
            return Response({ 'error': err.args[0] }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def payout_address(self, request):
        try:
            address_index = request.query_params.get('address_index', None)
            address, address_index = generate_payout_address(address_index=address_index)
            return Response({'payout_address': address, 'address_path': f'0/{address_index}'})
        except Exception as err:
            return Response({ 'error': err.args[0] }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def list_unspent_txns(self, request):
        wallet_hash = request.user.wallet_hash

        try:
            limit = int(request.query_params.get('limit', 0))
            page = int(request.query_params.get('page', 1))
            currency = request.query_params.get('currency')
            merchant_ids = request.query_params.getlist('merchant_ids', [])
            expire_status = request.query_params.get('status')
            
            pos_queryset = PosDevice.objects.filter(merchant__wallet_hash=wallet_hash)
            if len(merchant_ids) > 0:
                pos_queryset = pos_queryset.filter(merchant__id__in=merchant_ids)
            
            posids = pos_queryset.values_list('posid', flat=True)
            queryset = fetch_unspent_merchant_transactions(wallet_hash, posids)

            if expire_status:
                now = timezone.datetime.now()
                expiration_date = now - timezone.timedelta(days=30)

                if expire_status == 'expired':
                    # include only expired transactions
                    queryset = queryset.filter(tx_timestamp__lt=expiration_date)
                
                if expire_status == 'not-expired':
                    # exclude expired transactions
                    queryset = queryset.exclude(tx_timestamp__lt=expiration_date)

            count = queryset.count()
            total_pages = page
            if limit > 0:
                total_pages = math.ceil(count / limit)

            offset = (page - 1) * limit
            paged_queryset = queryset[offset:offset + limit]
            
            serializer = MerchantTransactionSerializer(paged_queryset, many=True, context={'wallet_hash': wallet_hash, 'currency': currency})
            data = {
                'unspent_transactions': serializer.data,
                'count': count,
                'total_pages': total_pages
            }
            return Response(data)
        
        except (ValidationError, Exception) as err:
            logger.exception(err)
            return Response({ 'error': err.args[0] }, status=status.HTTP_400_BAD_REQUEST)

    def create(self, request, *args, **kwargs):
        wallet = request.user
        txids =  request.data.get('txids', [])
        currency = request.data.get('currency', None)
        payment_method_id = request.data.get('payment_method_id')
        merchant_id = request.data.get('merchant_id')

        try:

            # limit to process only 500 txids per order
            if len(txids) > 500:
                raise ValidationError('cannot process more than 500 txids per order')
            
            with transaction.atomic():
                if len(txids) == 0:
                    raise ValidationError("missing required txids")
                
                merchant = Merchant.objects.get(id=merchant_id)
                currency_obj = FiatCurrency.objects.get(symbol=currency)
                current_market_price = MarketPrice.objects.get(currency=currency)
                payment_method = PaymentMethod.objects.get(wallet__wallet_hash=wallet.wallet_hash, id=payment_method_id)

                # create the cashout order
                order = CashOutOrder.objects.create( 
                    wallet=wallet,
                    merchant=merchant,
                    currency=currency_obj,
                    market_price=current_market_price.price
                )
                
                # create a snapshot of the payment method
                snapshot_data = {
                    'order': order,
                    'reference': payment_method,
                    'wallet': payment_method.wallet,
                    'payment_type': payment_method.payment_type
                }
                snapshot_payment_method = CashOutPaymentMethod.objects.create(**snapshot_data)
                fields = payment_method.fields.all()
                for field in fields:
                    # TODO: restrict field_reference allowed to payment_type
                    data = {
                        'payment_method': snapshot_payment_method,
                        'field_reference': field.field_reference,
                        'value': field.value
                    }
                    CashOutPaymentMethodField.objects.create(**data)

                order_serializer = CashOutOrderSerializer(order)
            
            # save input transactions as CashOutTransaction
            process_cashout_input_txns.apply_async(args=[
                order.id,
                wallet.wallet_hash,
                txids
            ])

            # generate the payout address
            payout_address, address_index = generate_payout_address()
            PayoutAddress.objects.get_or_create(
                    address=payout_address['receiving'],
                    address_index=address_index,
                    order=order,
                )
            
            return Response(order_serializer.data, status=status.HTTP_200_OK)
        
        except (ValidationError,
                Merchant.DoesNotExist,
                FiatCurrency.DoesNotExist,
                MarketPrice.DoesNotExist,
                PaymentMethod.DoesNotExist) as err:
            return Response({"error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
    
    def partial_update(self, request, *args, **kwargs):
        raise MethodNotAllowed(method='PATCH')

    def update(self, request, *args, **kwargs):
        if kwargs.get('partial', False):
            raise MethodNotAllowed(method='PATCH')
        raise MethodNotAllowed(method='PUT')

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed(method='DELETE')
    
    @action(detail=False, methods=['post'])
    def save_output_tx(self, request):
        try:
            wallet = request.user
            order_id = request.data.get('order_id')
            order = CashOutOrder.objects.filter(id=order_id, wallet__wallet_hash=wallet.wallet_hash)

            if not order.exists():
                return Response({"error": "order does not exist"}, status=status.HTTP_400_BAD_REQUEST)
            
            order = order.first()
            txid = request.data.get('txid')

            with transaction.atomic():
                txn = Transaction.objects.filter(txid=txid, wallet__wallet_hash=wallet.wallet_hash)
                wallet_history = WalletHistory.objects.filter(txid=txid, wallet__wallet_hash=wallet.wallet_hash, token__name="bch")
                
                data={
                    'order': order.id,
                    'txid': txid,
                    'record_type': CashOutTransaction.OUTGOING
                }

                if txn.exists():
                    data['transaction'] = txn.first().id

                if wallet_history.exists():
                    data["wallet_history"] = wallet_history.first().id

                serializer = BaseCashOutTransactionSerializer(data=data)
                if not serializer.is_valid():
                    raise ValidationError(serializer.errors)
                
                tx = serializer.save()
                serializer = BaseCashOutTransactionSerializer(tx)

                return Response(serializer.data, status=status.HTTP_200_OK)
        except (ValidationError, Exception) as err:
            return Response({"error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def calculate_payout_details(self, request):
        try:
            order_id = request.data.get('order_id')
            wallet_hash = request.user.wallet_hash
            txids = CashOutTransaction.objects.filter(order__id=order_id).values_list('txid', flat=True)
            process_cashout_input_txns.apply_async(args=[
                order_id,
                wallet_hash,
                list(txids)
            ])
            return Response(status=status.HTTP_200_OK)
        except CashOutOrder.DoesNotExist as err:
            return Response({"error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

class PaymentMethodViewSet(viewsets.ModelViewSet):
    queryset = PaymentMethod.objects.all()
    serializer_class = PaymentMethodSerializer
    authentication_classes = [ WalletAuthentication ]
    permission_classes = [ HasPaymentObjectPermission ]

    def list(self, request, *args, **kwargs):
        try:
            wallet = request.user
            if wallet == None:
                raise ValidationError('no credentials provided')
            
            currency = request.query_params.get('currency')
            currency = FiatCurrency.objects.get(symbol=currency)
            payment_type_ids = currency.payment_types.all().values_list('id')

            queryset = self.get_queryset().filter(wallet__wallet_hash=wallet.wallet_hash, payment_type__id__in=payment_type_ids)
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

        except (FiatCurrency.DoesNotExist, ValidationError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    def create(self, request, *args, **kwargs):        
        try:
            wallet_hash = request.user.wallet_hash
            payment_type_id = request.data.get('payment_type_id', None)
            values = request.data.get('values')
            
            if values is None or len(values) == 0:
                raise ValidationError('Empty payment method fields')
            
            wallet = Wallet.objects.get(wallet_hash=wallet_hash)
            payment_type = PaymentType.objects.get(id=payment_type_id)

            data = {
                'wallet': wallet,
                'payment_type': payment_type
            }

            with transaction.atomic():
                # create payment method
                payment_method = PaymentMethod.objects.create(**data)
                # create payment method fields
                for field in values:
                    # TODO: restrict field_reference allowed to payment_type
                    if field['value']:
                        field_ref = PaymentTypeField.objects.get(id=field['field_reference'])
                        data = {
                            'payment_method': payment_method,
                            'field_reference': field_ref,
                            'value': field['value']
                        }
                        PaymentMethodField.objects.create(**data)
                
            serializer = self.serializer_class(payment_method)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, pk):
        try:
            payment_method = self.get_queryset().get(pk=pk)
        
            data = request.data.copy()
            payment_fields = data.get('payment_fields')
            if payment_fields is None or len(payment_fields) == 0:
                raise ValidationError('Empty payment method fields')

            with transaction.atomic():
                for field in payment_fields:
                    field_id = field.get('id')
                    if field_id:
                        payment_method_field = PaymentMethodField.objects.get(id=field_id)
                        payment_method_field.value = field.get('value')
                        payment_method_field.save()
                    elif field.get('value') and field.get('field_reference'):
                        field_ref = PaymentTypeField.objects.get(id=field.get('field_reference'))
                        data = {
                            'payment_method': payment_method,
                            'field_reference': field_ref,
                            'value': field.get('value')
                        }
                        PaymentMethodField.objects.create(**data)

            serializer = PaymentMethodSerializer(payment_method)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
