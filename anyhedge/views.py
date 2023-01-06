from django.db import models
from django_filters import rest_framework as filters
from rest_framework import (
    generics,
    viewsets,
    mixins,
    decorators,
    serializers,
    status,
)
from rest_framework.response import Response
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

from .models import HedgePositionOffer
from .serializers import (
    FundingProposalSerializer,
    LongAccountSerializer,
    MutualRedemptionSerializer,
    HedgePositionSerializer,
    HedgePositionOfferCounterPartySerializer,
    HedgePositionOfferSerializer,
    MatchHedgePositionSerializer,
    SettleHedgePositionOfferSerializer,
    SubmitFundingTransactionSerializer,
    FundGeneralProcotolLPContractSerializer,

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
from .tasks import (
    complete_contract_funding,
    validate_contract_funding,
    update_contract_settlement,
    redeem_contract,
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


    @decorators.action(methods=["get"], detail=False)
    def summary(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.annotate(
            nominal_unit_sats = queryset.Annotations.nominal_unit_sats,
            long_sats = queryset.Annotations.long_sats,
        )
        queryset = queryset.values('oracle_pubkey')
        queryset.query.clear_ordering(force_empty=True)
        queryset = queryset.annotate(
            total_hedge_unit_sats=models.Sum("nominal_unit_sats"),
            total_long_sats=models.Sum("long_sats"),
        )
        data = queryset.values('oracle_pubkey', 'total_hedge_unit_sats', 'total_long_sats')
        return Response(data, status=status.HTTP_200_OK)


    @swagger_auto_schema(method="post", request_body=FundingProposalSerializer, responses={201: serializer_class})
    @decorators.action(methods=["post"], detail=False)
    def submit_funding_proposal(self, request):
        serializer = FundingProposalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        funding_proposal_obj = serializer.instance
        hedge_obj = None
        try:
            hedge_obj = funding_proposal_obj.hedge_position
        except funding_proposal_obj.__class__.hedge_position.RelatedObjectDoesNotExist: 
            hedge_obj = serializer.instance.long_position

        contract_funding_status = "incomplete"
        if hedge_obj.hedge_funding_proposal and hedge_obj.long_funding_proposal:
            funding_task_response = complete_contract_funding(hedge_obj.address)

            contract_funding_status = f"{funding_task_response}"

            funding_tx_hash = funding_task_response.get("tx_hash", None)
            if funding_tx_hash:
                hedge_obj.funding_tx_hash = funding_tx_hash
                hedge_obj.save()
                validate_contract_funding.delay(hedge_obj.address)

        return Response(
            self.serializer_class(hedge_obj).data,
            headers={ 'funding-status': contract_funding_status },
        )

    @swagger_auto_schema(method="post", request_body=serializers.Serializer, responses={200: serializer_class})
    @decorators.action(methods=["post"], detail=True)
    def complete_funding(self, request, *args, **kwargs):
        instance = self.get_object()
        funding_task_response = complete_contract_funding(instance.address)
        if funding_task_response["success"]:
            instance.refresh_from_db()
            validate_contract_funding.delay(instance.address)
            return Response(self.serializer_class(instance).data)
        else:
            error_data = funding_task_response["error"]
            if not isinstance(error_data, list):
                error_data = [error_data]
            return Response(error_data, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(method="post", request_body=serializers.Serializer, responses={200: serializer_class})
    @decorators.action(methods=["post"], detail=True)
    def validate_contract_funding(self, request, *args, **kwargs):
        instance = self.get_object()
        validate_contract_funding_response = validate_contract_funding(instance.address)
        if validate_contract_funding_response["success"]:
            instance.refresh_from_db()
            return Response(self.serializer_class(instance).data)
        else:
            error_data = validate_contract_funding_response["error"]
            if not isinstance(error_data, list):
                error_data = [error_data]
            return Response(error_data, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(method="post", request_body=SubmitFundingTransactionSerializer, responses={201: serializer_class})
    @decorators.action(methods=["post"], detail=False)
    def set_funding_tx(self, request):
        serializer = SubmitFundingTransactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        hedge_obj = serializer.save()
        return Response(self.serializer_class(hedge_obj).data)

    @swagger_auto_schema(method="post", request_body=MutualRedemptionSerializer, responses={201: serializer_class})
    @decorators.action(methods=["post"], detail=True)
    def mutual_redemption(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            if instance.settlement:
                return Response(["Hedge position is already settled"], status=status.HTTP_400_BAD_REQUEST)
        except instance.__class__.settlement.RelatedObjectDoesNotExist:
            pass

        try:
            if instance.mutual_redemption and instance.mutual_redemption.tx_hash:
                update_contract_settlement.delay(instance.address)
                return Response(["Mutual redemption is already completed"], status=status.HTTP_400_BAD_REQUEST)
        except instance.__class__.mutual_redemption.RelatedObjectDoesNotExist:
            pass

        serializer = MutualRedemptionSerializer(data=request.data, hedge_position=instance)
        serializer.is_valid(raise_exception=True)
        mutual_redemption_obj = serializer.save()
        instance = mutual_redemption_obj.hedge_position

        if mutual_redemption_obj.hedge_schnorr_sig and mutual_redemption_obj.long_schnorr_sig:    
            redeem_contract_response = redeem_contract(instance.address)
            if not redeem_contract_response["success"]:
                error = "Encountered error in redeeming contract"
                if redeem_contract_response.get("error", None):
                    error = redeem_contract_response["error"]
                return Response([error], status=status.HTTP_400_BAD_REQUEST)
            update_contract_settlement.delay(instance.address)

        instance.refresh_from_db()
        return Response(self.serializer_class(instance).data)

    @swagger_auto_schema(method="post", request_body=serializers.Serializer, responses={201: serializer_class})
    @decorators.action(methods=["post"], detail=True)
    def complete_mutual_redemption(self, request):
        instance = self.get_object()
        try:
            instance.mutual_redemption
        except HedgePositionSerializer.Meta.model.mutual_redemption.RelatedObjectDoesNotExist:
            return Response(["no mutual redemption found"], status=status.HTTP_400_BAD_REQUEST)

        if not instance.mutual_redemption.hedge_schnorr_sig or not instance.mutual_redemption.long_schnorr_sig:
            return Response(["incomplete signatures"], status=status.HTTP_400_BAD_REQUEST)

        redeem_contract_response = redeem_contract(instance.address)
        if not redeem_contract_response["success"]:
            error = "Encountered error in redeeming contract"
            if redeem_contract_response.get("error", None):
                error = redeem_contract_response["error"]
            return Response([error], status=status.HTTP_400_BAD_REQUEST)

        update_contract_settlement.delay(instance.address)
        instance.refresh_from_db()
        return Response(self.serializer_class(instance).data)


    @swagger_auto_schema(method="post", request_body=FundGeneralProcotolLPContractSerializer, responses={201: serializer_class})
    @decorators.action(methods=["post"], detail=False)
    def fund_gp_lp_contract(self, request):
        serializer = FundGeneralProcotolLPContractSerializer(data=request.data)
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

    @swagger_auto_schema(method="post", request_body=HedgePositionOfferCounterPartySerializer, responses={200: serializer_class})
    @decorators.action(methods=["post"], detail=True)
    def accept_offer(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = HedgePositionOfferCounterPartySerializer(
            data=request.data,
            hedge_position_offer=instance
        )
        serializer.is_valid(raise_exception=True)
        counter_party_info = serializer.save()

        serializer = self.get_serializer(counter_party_info.hedge_position_offer)
        return Response(serializer.data)

    @swagger_auto_schema(method="post", responses={200: serializer_class})
    @decorators.action(methods=["post"], detail=True)
    def cancel_accept_offer(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != HedgePositionOffer.STATUS_ACCEPTED:
            return Response(["hedge position offer is not in accepted state"],status=400)
        try:
            instance.counter_party_info.delete()
        except HedgePositionOffer.counter_party_info.RelatedObjectDoesNotExist:
            pass
        instance.status = HedgePositionOffer.STATUS_PENDING
        instance.save()
        instance.refresh_from_db()

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @swagger_auto_schema(method="post", request_body=SettleHedgePositionOfferSerializer, responses={201: HedgePositionSerializer})
    @decorators.action(methods=["post"], detail=True)
    def settle_offer(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = SettleHedgePositionOfferSerializer(
            data=request.data,
            hedge_position_offer=instance,
        )
        serializer.is_valid(raise_exception=True)
        hedge_position = serializer.save()
        serializer = HedgePositionSerializer(hedge_position)
        return Response(serializer.data)

    @swagger_auto_schema(method="post", request_body=MatchHedgePositionSerializer, response={200: MatchHedgePositionSerializer})
    @decorators.action(methods=["post"], detail=False)
    def find_match(self, request, *args, **kwargs):
        serializer = MatchHedgePositionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.find_match()
        serializer = MatchHedgePositionSerializer(data)
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
