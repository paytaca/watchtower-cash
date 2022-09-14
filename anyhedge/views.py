from django_filters import rest_framework as filters
from rest_framework import (
    generics,
    viewsets,
    mixins,
    decorators,
    status,
)
from rest_framework.response import Response
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

from .serializers import (
    FundingProposalSerializer,
    LongAccountSerializer,
    HedgePositionSerializer,
    HedgePositionOfferSerializer,
    SettleHedgePositionOfferSerializer,
    SubmitFundingTransactionSerializer,

    OracleSerializer,
    PriceOracleMessageSerializer,
)
from .filters import (
    LongAccountFilter,
    HedgePositionFilter,
    HedgePositionOfferFilter,

    OracleFilter,
    PriceOracleMessageFilter,
)
from .pagination import CustomLimitOffsetPagination
from .utils.websocket import (
    send_hedge_position_offer_update,
)


class LongAccountViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
):
    lookup_field="wallet_hash"
    serializer_class = LongAccountSerializer
    pagination_class = CustomLimitOffsetPagination

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = LongAccountFilter

    def get_queryset(self):
        return LongAccountSerializer.Meta.model.objects.all()


# Create your views here.
class HedgePositionViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
):
    lookup_field="address"
    serializer_class = HedgePositionSerializer
    pagination_class = CustomLimitOffsetPagination

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = HedgePositionFilter

    def get_queryset(self):
        return HedgePositionSerializer.Meta.model.objects.all()

    @swagger_auto_schema(method="post", request_body=FundingProposalSerializer, responses={201: serializer_class})
    @decorators.action(methods=["post"], detail=False)
    def submit_funding_proposal(self, request):
        serializer = FundingProposalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        hedge_obj = serializer.instance.hedge_position or serializer.instance.long_position
        return Response(self.serializer_class(hedge_obj).data)

    @swagger_auto_schema(method="post", request_body=SubmitFundingTransactionSerializer, responses={201: serializer_class})
    @decorators.action(methods=["post"], detail=False)
    def set_funding_tx(self, request):
        serializer = SubmitFundingTransactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        hedge_obj = serializer.save()
        return Response(self.serializer_class(hedge_obj).data)


class HedgePositionOfferViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
):
    serializer_class = HedgePositionOfferSerializer
    pagination_class = CustomLimitOffsetPagination

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = HedgePositionOfferFilter

    def get_queryset(self):
        return HedgePositionOfferSerializer.Meta.model.objects.all()

    @swagger_auto_schema(method="post", request_body=openapi.Schema(type=openapi.TYPE_OBJECT), responses={201: serializer_class})
    @decorators.action(methods=["post"], detail=True)
    def cancel_hedge_request(self, request):
        instance = self.get_object()

        if instance.status == HedgePositionOfferSerializer.Meta.model.STATUS_SETTLED:
            return Response(['Position offer already settled'], status=status.HTTP_400_BAD_REQUEST)

        instance.status = HedgePositionOfferSerializer.Meta.model.STATUS_CANCELLED
        instance.save()
        send_hedge_position_offer_update(instance, action="cancel")

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @swagger_auto_schema(method="post", request_body=SettleHedgePositionOfferSerializer, responses={201: serializer_class})
    @decorators.action(methods=["post"], detail=True)
    def settle_offer(self, request):
        instance = self.get_object()
        serializer = SettleHedgePositionOfferSerializer(
            data=request.data,
            hedge_position_offer=instance,
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class OracleViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    lookup_field="pubkey"
    serializer_class = OracleSerializer
    pagination_class = CustomLimitOffsetPagination

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = OracleFilter

    def get_queryset(self):
        return OracleSerializer.Meta.model.objects.all()


class PriceOracleMessageViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
):
    serializer_class = PriceOracleMessageSerializer
    pagination_class = CustomLimitOffsetPagination

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = PriceOracleMessageFilter


    def get_queryset(self):
        return PriceOracleMessageSerializer.Meta.model.objects.all()
