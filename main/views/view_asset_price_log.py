import time
import logging
import celery
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.response import Response
from rest_framework import status, exceptions

from watchtower.celery import app as celery_app

from rest_framework.permissions import AllowAny
from rest_framework import generics
from main import serializers
from main.models import AssetPriceLog
from main.tasks import get_latest_bch_price, market_price_task



LOGGER = logging.getLogger(__name__)


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


class LatestMarketPriceView(generics.GenericAPIView):
    serializer_class = serializers.AssetPriceLogSerializer
    permission_classes = [AllowAny,]

    @swagger_auto_schema(
        responses = {200: serializer_class(many=True)},
        manual_parameters=[
            openapi.Parameter(name="currencies", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, required=True),
            openapi.Parameter(name="coin_ids", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, required=True),
        ]
    )
    def get(self, request, *args, **kwargs):
        currencies = request.query_params.get('currencies', '')
        coin_ids = request.query_params.get('coin_ids', '')

        currencies_list = [currency.strip().upper() for currency in currencies.split(",")]
        currencies_list = [c for c in currencies_list if c] # remove empty
        currencies_list = list(set(currencies_list)) # remove duplicates

        coin_ids_list = [coin_id.strip().lower() for coin_id in coin_ids.split(",")]
        coin_ids_list = [c for c in coin_ids_list if c] # remove empty
        coin_ids_list = list(set(coin_ids_list)) # remove duplicates


        if not currencies_list and not coin_ids_list:
            raise exceptions.APIException("currencies and coin_ids not provided")
        elif not currencies_list:
            raise exceptions.APIException("currencies not provided")
        elif not coin_ids_list:
            raise exceptions.APIException("coin_ids not provided")


        # --- flatten 2 lists into list of pairs ---
        pair_names = set()
        for currency in currencies_list:
            for coin_id in coin_ids_list:
                pair_name = market_price_task.construct_pair(
                    coin_id=coin_id, currency=currency,
                )
                pair_names.add(pair_name)

        LOGGER.info(f"pair_names={pair_names}")


        # --- resolve pairs fetched by running tasks and pairs the need to be queued ----
        pair_name_asset_price_logs_map = {}
        running_task_ids = set()
        pairs_to_queue = set()
        for pair_name in pair_names:
            asset_price_log = market_price_task.get_latest(pair_name=pair_name)
            if asset_price_log:
                pair_name_asset_price_logs_map[pair_name] = asset_price_log
                continue

            task_id = market_price_task.get_running_task_id(pair_name)
            if task_id:
                running_task_ids.add(task_id)
                continue

            pairs_to_queue.add(pair_name)

        LOGGER.info(f"running_task_ids={running_task_ids} | pairs_to_queue={pairs_to_queue} | pair_name_asset_price_logs_map={pair_name_asset_price_logs_map}")


        # --- queue pairs, wait(for throttling), and run market price task ---
        if pairs_to_queue:
            market_price_task.queue_pairs(*pairs_to_queue)
            wait_time = market_price_task.get_wait_time()
            LOGGER.info(f"wait_time={wait_time}")

            run_task = False
            if wait_time > 0:
                time.sleep(wait_time)

            # --- re check running tasks, task might have executed while this ---
            queued_task_ids = []
            for pair_name in pairs_to_queue:
                result = market_price_task.get_running_task_id(pair_name)
                if result:
                    running_task_ids.add(result)
                queued_task_ids.append(result)

            if not all(queued_task_ids):
                market_prices_task_obj = market_price_task.delay()
                running_task_ids.add(market_prices_task_obj.id)

        LOGGER.info(f"updated running_task_ids={running_task_ids}")

        # --- compile tasks of pairs that are being fetched ---
        self.wait_task_ids(running_task_ids)

        # --- refetch latest price data for all pairs(even pairs resolved earlier in this funciton) ---
        for pair_name in pair_names:
            asset_price_log = market_price_task.get_latest(pair_name=pair_name)
            if asset_price_log:
                pair_name_asset_price_logs_map[pair_name] = asset_price_log
                continue

        # --- serialization of results ---
        price_logs = [*pair_name_asset_price_logs_map.values()]
        serializer = self.serializer_class(price_logs, many=True)
        return Response(serializer.data)

    def wait_task_ids(self, task_ids:list, max_timeout=30):
        tasks = [celery_app.AsyncResult(task_id) for task_id in task_ids]
        start_time = time.time()
        try:
            for task in tasks:
                task.get(timeout=max_timeout)
                if time.time() - start_time >= max_timeout:
                    break
        except Exception as exception:
            LOGGER.exception(exception)


class PriceChartView(generics.GenericAPIView):
    serializer_class = serializers.AssetPriceChartSerializer
    permission_classes = [AllowAny,]
    
    @swagger_auto_schema(
        responses = {200: serializer_class(many=True)},
        manual_parameters=[
            openapi.Parameter(name="vs_currency", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, required=True),
            openapi.Parameter(name="days", type=openapi.TYPE_INTEGER, in_=openapi.IN_QUERY, required=True),
        ]
    )
    def get(self, request, *args, **kwargs):
        relative_currency = kwargs.get('relative_currency', 'bitcoin-cash')
        vs_currency = request.query_params.get('vs_currency', 'USD')
        days = request.query_params.get('days', 1)
        days = int(days)

        self.get_latest_pair(coin_id=relative_currency, currency=vs_currency)

        if relative_currency == 'bitcoin-cash':
            relative_currency = 'BCH'

        min_timestamp = timezone.now() - timezone.timedelta(days=days)
        filter_kwargs = {
            'currency': vs_currency,
            'relative_currency': relative_currency,
            'timestamp__gte': min_timestamp,
        }
        
        if vs_currency == 'ARS':
            filter_kwargs['source'] = 'coingecko-yadio'
            
        data = AssetPriceLog.objects.filter(**filter_kwargs).order_by("-timestamp").values("timestamp", "price_value")

        serializer = self.serializer_class(data, many=True)
        return Response(serializer.data)

    def get_latest_pair(self, coin_id:str, currency:str):
        pair_name = market_price_task.construct_pair(
            coin_id=coin_id, currency=currency,
        )
        asset_price_log = market_price_task.get_latest(pair_name=pair_name)

        if not asset_price_log:
            market_price_task.queue_pairs(pair_name)
            market_price_task.delay()

        return market_price_task.get_latest(pair_name=pair_name)
