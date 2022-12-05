from django.db.models import (
    F, Value,
    Func,
    ExpressionWrapper,
    CharField,
)
from django.db import transaction
from django_filters import rest_framework as filters
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets, mixins, decorators
from rest_framework import status
from .serializers import (
    PosDeviceLinkSerializer,
    PosDeviceLinkRequestSerializer,
    LinkedDeviceInfoSerializer,
    UnlinkDeviceSerializer,
    UnlinkDeviceRequestSerializer,
    POSPaymentSerializer,
    POSPaymentResponseSerializer,
    PosDeviceSerializer,
    MerchantSerializer,
    BranchSerializer,
)
from .filters import (
    PosDevicetFilter,
    BranchFilter,
)
from .pagination import CustomLimitOffsetPagination
from .utils.websocket import send_device_update



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

    def get_queryset(self):
        return self.serializer_class.Meta.model.objects.annotate(
            wallet_hash_posid=ExpressionWrapper(
                Func(F("wallet_hash"), Value(":"), F("posid"), function="CONCAT"),
                output_field=CharField(max_length=75),
            )
        ).all()

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


class MerchantViewSet(
    viewsets.GenericViewSet,
    # mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
):
    serializer_class = MerchantSerializer
    lookup_field="wallet_hash"
    pagination_class = CustomLimitOffsetPagination

    def get_queryset(self):
        return self.serializer_class.Meta.model.objects.all()


class BranchViewSet(viewsets.ModelViewSet):
    serializer_class = BranchSerializer
    pagination_class = CustomLimitOffsetPagination

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = BranchFilter

    def get_queryset(self):
        return self.serializer_class.Meta.model.objects.all()
