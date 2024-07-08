from django.db.models import (
    F, Value,
    Func,
    ExpressionWrapper,
    CharField,
)
from django.db import transaction
from django.utils import timezone
from django_filters import rest_framework as filters
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets, mixins, decorators, exceptions, permissions
from rest_framework import status
from .serializers import *
from .filters import *
from .permissions import HasMerchantObjectPermission
from .pagination import CustomLimitOffsetPagination
from .utils.websocket import send_device_update
from .utils.report import SalesSummary

from .models import Location, Category

from authentication.token import WalletAuthentication

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
    filterset_class = PosDevicetFilter

    permission_classes = [
        HasMerchantObjectPermission,
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
        code_ttl = 60 * 5
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
            return Response(status=400)
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
        HasMerchantObjectPermission,
    ]
    authentication_classes = [
        WalletAuthentication,
    ]

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(name="active", type=openapi.TYPE_BOOLEAN, in_=openapi.IN_QUERY, default=False),
            openapi.Parameter(name="verified", type=openapi.TYPE_BOOLEAN, in_=openapi.IN_QUERY, default=False),
            openapi.Parameter(name="name", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, required=False),
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
        if instance.devices.count():
            raise exceptions.ValidationError("Unable to remove merchant linked to a device")
        return super().destroy(request, *args, **kwargs)

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
            
        if self.action == 'list':
            __active = self.request.query_params.get('active', '')
            __verified = self.request.query_params.get('verified', '')
            __name = self.request.query_params.get('name', '')

            active = __active.lower() == 'true' or False
            verified = __verified.lower() == 'true' or False
            name = __name.lower()

            queryset = queryset.filter(
                active=active,
                verified=verified
            )
            if name:
                queryset = queryset.filter(name__icontains=name)
        return queryset


class BranchViewSet(viewsets.ModelViewSet):
    serializer_class = BranchSerializer
    pagination_class = CustomLimitOffsetPagination

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = BranchFilter

    permission_classes = [
        HasMerchantObjectPermission,
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
