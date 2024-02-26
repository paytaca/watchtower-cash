import logging
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.response import Response
from rest_framework import status, exceptions


from rest_framework.permissions import AllowAny
from rest_framework import generics
from main import serializers
from main.models import AssetPriceLog
from main.tasks import get_latest_bch_price




class LatestBCHPriceView(generics.GenericAPIView):
    serializer_class = serializers.AssetPriceLogSerializer
    permission_classes = [AllowAny,]

    @swagger_auto_schema(
        responses = {200: serializer_class(many=True)},
        manual_parameters=[
            openapi.Parameter(name="currencies", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, required=True),
        ]
    )
    def get(self, request, *args, **kwargs):
        currencies = request.query_params.get('currencies', '')

        currencies_list = [currency.strip().upper() for currency in currencies.split(",")]
        currencies_list = [c for c in currencies_list if c] # remove empty
        currencies_list = list(set(currencies_list)) # remove duplicates

        if not currencies_list:
            raise exceptions.APIException("currencies not provided")

        price_logs = []
        for currency in currencies_list:
            try:
                result = get_latest_bch_price(currency)
                if isinstance(result, AssetPriceLog):
                    price_logs.append(result)
            except Exception as exception:
                logging.exception(exception)
        serializer = self.serializer_class(price_logs, many=True)
        return Response(serializer.data)
