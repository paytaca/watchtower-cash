from rest_framework import viewsets, mixins, decorators
from rest_framework.response import Response
from django_filters import rest_framework as filters

from stablehedge import models
from stablehedge import serializers

from stablehedge.filters import (
    RedemptionContractFilter,
)

from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from stablehedge.js.runner import ScriptFunctions
from anyhedge import models as anyhedge_models



class FiatTokenViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    lookup_field = "category"
    serializer_class = serializers.FiatTokenSerializer

    def get_queryset(self):
        return models.FiatToken.objects.all()


class RedemptionContractViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
):
    lookup_field = "address"
    serializer_class = serializers.RedemptionContractSerializer

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = RedemptionContractFilter

    def get_queryset(self):
        return models.RedemptionContract.objects \
            .annotate_redeemable() \
            .annotate_reserve_supply() \
            .all()

    @decorators.action(
        methods=["post"], detail=False,
        serializer_class=serializers.SweepRedemptionContractSerializer,
    )
    def sweep(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(result)

    @decorators.action(
        methods=["post"], detail=False,
        serializer_class=serializers.RedemptionContractTransactionSerializer,
    )
    def transaction(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(serializer.data)


class TestUtilsViewSet(viewsets.GenericViewSet):
    @swagger_auto_schema(
        method="get",
        manual_parameters=[
            openapi.Parameter('price', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('wif', openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Optional"),
            openapi.Parameter('save', openapi.IN_QUERY, type=openapi.TYPE_BOOLEAN),
        ],
    )
    @decorators.action(methods=["get"], detail=False)
    def price_message(self, request, *args, **kwargs):
        save = str(request.query_params.get("save", "")).lower().strip() == "true"
        wif = request.query_params.get("wif", None) or None
        try:
            price = int(request.query_params.get("price"))
        except (TypeError, ValueError):
            price = hash(request) % 2 ** 32 # almost random

        result = ScriptFunctions.generatePriceMessage(dict(price=price, wif=wif))

        if save:
            msg_timestamp = timezone.datetime.fromtimestamp(result["priceData"]["timestamp"] / 1000)
            msg_timestamp = timezone.make_aware(msg_timestamp)
            anyhedge_models.PriceOracleMessage.objects.update_or_create(
                pubkey=result["publicKey"],
                message=result["priceMessage"],
                defaults=dict(
                    signature=result["signature"],
                    message_timestamp=msg_timestamp,
                    price_value=result["priceData"]["price"],
                    price_sequence=result["priceData"]["dataSequence"],
                    message_sequence=result["priceData"]["msgSequence"],
                ),
            )

        result.pop("privateKey", None)
        return Response(result)
