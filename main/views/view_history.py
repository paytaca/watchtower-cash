from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import (
    F, Q, Value,
    OuterRef, Subquery,
    Func, Count,
    BigIntegerField,
)
from django.db.models.functions import Substr, Cast, Floor
from django.db.models import ExpressionWrapper, FloatField
from rest_framework import status
from main.models import Wallet, Address, WalletHistory
from django.core.paginator import Paginator
from main.serializers import PaginatedWalletHistorySerializer
from main.throttles import RebuildHistoryThrottle
from main.tasks import (
    rebuild_wallet_history
)

POS_ID_MAX_DIGITS = 4

class WalletHistoryView(APIView):

    @swagger_auto_schema(
        responses={200: PaginatedWalletHistorySerializer},
        manual_parameters=[
            openapi.Parameter(name="page", type=openapi.TYPE_NUMBER, in_=openapi.IN_QUERY, default=1),
            openapi.Parameter(name="posid", type=openapi.TYPE_NUMBER, in_=openapi.IN_QUERY, required=False),
            openapi.Parameter(name="type", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, default="all", enum=["incoming", "outgoing"]),
            openapi.Parameter(name="txids", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, required=False),
            openapi.Parameter(name="attr", type=openapi.TYPE_BOOLEAN, in_=openapi.IN_QUERY, default=True, required=False),
        ]
    )
    def get(self, request, *args, **kwargs):
        wallet_hash = kwargs.get('wallethash', None)
        token_id_or_category = kwargs.get('tokenid_or_category', None)
        category = kwargs.get('category', None)
        index = kwargs.get('index', None)
        txid = kwargs.get('txid', None)
        page = request.query_params.get('page', 1)
        record_type = request.query_params.get('type', 'all')
        posid = request.query_params.get("posid", None)
        txids = request.query_params.get("txids", "")
        include_attrs = str(request.query_params.get("exclude_attr", "true")).strip().lower() == "true"
        
        is_cashtoken_nft = False
        if index and txid:
            index = int(index)
            is_cashtoken_nft = True

        if isinstance(txids, str):
            txids = [txid for txid in txids.split(",") if txid]


        qs = WalletHistory.objects.filter(wallet__wallet_hash=wallet_hash).exclude(amount=0)
        
        if record_type in ['incoming', 'outgoing']:
            qs = qs.filter(record_type=record_type)
        if len(txids):
            qs = qs.filter(txid__in=txids)

        if posid:
            try:
                posid = int(posid)
                posid = str(posid)
                pad = "0" * (POS_ID_MAX_DIGITS-len(posid))
                posid = pad + posid
            except (TypeError, ValueError):
                return Response(data=[f"invalid POS ID: {type(posid)}({posid})"], status=status.HTTP_400_BAD_REQUEST)

            addresses = Address.objects.filter(
                wallet_id=OuterRef("wallet_id"),
                address_path__iregex=f"((0|1)/)?0*\d+{posid}",
            ).values("address").distinct()
            addresses_subquery = Func(Subquery(addresses), function="array")
            qs = qs.filter(
                Q(senders__overlap=addresses_subquery) | Q(recipients__overlap=addresses_subquery),
            )

        wallet = Wallet.objects.get(wallet_hash=wallet_hash)
        qs = qs.order_by(F('tx_timestamp').desc(nulls_last=True), F('date_created').desc(nulls_last=True))

        if include_attrs:
            qs = qs.annotate_attributes(
                Q(wallet_hash="") | Q(wallet_hash=wallet_hash),
            )
        else:
            qs = qs.annotate_empty_attributes()

        if token_id_or_category or category:
            if wallet.wallet_type == 'bch':
                if is_cashtoken_nft:
                    qs = qs.filter(
                        cashtoken_nft__category=category,
                        cashtoken_nft__current_index=index,
                        cashtoken_nft__current_txid=txid
                    )
                    history = qs.annotate(
                        _token=F('cashtoken_nft__category')
                    )
                else:
                    qs = qs.filter(cashtoken_ft__category=token_id_or_category)
                    history = qs.annotate(
                        _token=F('cashtoken_ft__category'),
                        amount=ExpressionWrapper(
                            #F('amount') / (10 ** F('cashtoken_ft__info__decimals')),
                            F('amount'),
                            output_field=FloatField()
                        )
                    )

                history = history.rename_annotations(
                    _token='token_id_or_category'
                ).values(
                    'record_type',
                    'txid',
                    'amount',
                    'token',
                    'tx_fee',
                    'senders',
                    'recipients',
                    'date_created',
                    'tx_timestamp',
                    'usd_price',
                    'market_prices',
                    'attributes',
                )
            else:
                qs = qs.filter(token__tokenid=token_id_or_category)

                history = qs.annotate(
                    _token=F('token__tokenid')
                ).rename_annotations(
                    _token='token_id_or_category'
                ).values(
                    'record_type',
                    'txid',
                    'amount',
                    'token',
                    'tx_fee',
                    'senders',
                    'recipients',
                    'date_created',
                    'tx_timestamp',
                    'usd_price',
                    'market_prices',
                    'attributes',
                )
        else:
            qs = qs.filter(token__name='bch')
            history = qs.values(
                'record_type',
                'txid',
                'amount',
                'tx_fee',
                'senders',
                'recipients',
                'date_created',
                'tx_timestamp',
                'usd_price',
                'market_prices',
                'attributes',
            )

        if wallet.version == 1:
            return Response(data=history, status=status.HTTP_200_OK)
        else:
            pages = Paginator(history, 10)
            page_obj = pages.page(int(page))
            data = {
                'history': page_obj.object_list,
                'page': page,
                'num_pages': pages.num_pages,
                'has_next': page_obj.has_next()
            }
            return Response(data=data, status=status.HTTP_200_OK)


class LastAddressIndexView(APIView):
    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(name="with_tx", type=openapi.TYPE_BOOLEAN, in_=openapi.IN_QUERY, default=False),
            openapi.Parameter(name="exclude_pos", type=openapi.TYPE_BOOLEAN, in_=openapi.IN_QUERY, default=False),
            openapi.Parameter(name="posid", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, required=False),
        ]
    )
    def get(self, request, *args, **kwargs):
        """
            Get the last receiving address index of a wallet
        """
        wallet_hash = kwargs.get("wallethash", None)
        with_tx = request.query_params.get("with_tx", False)
        exclude_pos = request.query_params.get("exclude_pos", False)
        posid = request.query_params.get("posid", None)
        if posid is not None:
            try:
                posid = int(posid)
            except (TypeError, ValueError):
                return Response(data=[f"invalid POS ID: {type(posid)}({posid})"], status=status.HTTP_400_BAD_REQUEST)

        queryset = Address.objects.annotate(
            address_index = Cast(Substr(F("address_path"), Value("0/(\d+)")), BigIntegerField()),
        ).filter(
            wallet__wallet_hash=wallet_hash,
            address_index__isnull=False,
        )
        fields = ["address", "address_index"]
        ordering = ["-address_index"]

        if isinstance(with_tx, str) and with_tx.lower() == "false":
            with_tx = False

        if isinstance(exclude_pos, str) and exclude_pos.lower() == "false":
            exclude_pos = False

        if with_tx:
            queryset = queryset.annotate(tx_count = Count("transactions__txid", distinct=True))
            queryset = queryset.filter(tx_count__gt=0)
            ordering = ["-tx_count", "-address_index"]
            fields.append("tx_count")

        if isinstance(posid, int) and posid >= 0:
            POSID_MULTIPLIER = Value(10 ** POS_ID_MAX_DIGITS)
            queryset = queryset.annotate(posid=F("address_index") % POSID_MULTIPLIER)
            queryset = queryset.annotate(payment_index=Floor(F("address_index") / POSID_MULTIPLIER))
            queryset = queryset.filter(address_index__gte=POSID_MULTIPLIER)
            queryset = queryset.filter(posid=posid)
            # queryset = queryset.filter(address_index__gte=models.Value(0))
            fields.append("posid")
            fields.append("payment_index")
        elif exclude_pos:
            POSID_MULTIPLIER = Value(10 ** POS_ID_MAX_DIGITS)
            MAX_UNHARDENED_ADDRESS_INDEX = Value(2**32-1)
            queryset = queryset.exclude(
                address_index__gte=POSID_MULTIPLIER,
                address_index__lte=MAX_UNHARDENED_ADDRESS_INDEX,
            )

        queryset = queryset.values(*fields).order_by(*ordering)
        if len(queryset):
            address = queryset[0]
        else:
            address = None

        data = {
            "wallet_hash": wallet_hash,
            "address": address,
        }

        return Response(data)


class RebuildHistoryView(APIView):
    throttle_classes = [RebuildHistoryThrottle]

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(name="background", type=openapi.TYPE_BOOLEAN, in_=openapi.IN_QUERY, default=False),
        ]
    )
    def get(self, request, *args, **kwargs):
        wallet_hash = kwargs.get('wallethash', '')
        background = request.query_params.get("background", None)
        if isinstance(background, str) and background.lower() == "false":
            background = False

        try:
            wallet = Wallet.objects.get(wallet_hash=wallet_hash)
        except Wallet.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if background:
            task = rebuild_wallet_history.delay(wallet.wallet_hash)
            return Response({ "task_id": task.id }, status = status.HTTP_202_ACCEPTED)

        rebuild_wallet_history(wallet.wallet_hash)
        return Response(data={'success': True}, status=status.HTTP_200_OK)
