from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import (
    F, Q, Value, Count,
    BigIntegerField,
)
import pickle
import base64
from django.conf import settings
from django.db.models.functions import Substr, Cast, Floor
from django.db.models import ExpressionWrapper, FloatField, Subquery, OuterRef
from rest_framework import status
from main.models import Wallet, Address, WalletHistory, ContractHistory, TransactionMetaAttribute
from django.core.paginator import Paginator
from main.serializers import PaginatedWalletHistorySerializer
from main.throttles import RebuildHistoryThrottle
from main.tasks import (
    rebuild_wallet_history
)

POS_ID_MAX_DIGITS = 4


def get_memo_subquery(wallet_hash):
    """Create a subquery to get encrypted memo for each transaction."""
    from memos.models import Memo
    return Memo.objects.filter(
        txid=OuterRef('txid'),
        wallet_hash=wallet_hash
    ).values('note')[:1]


def expand_token_from_dict(item, token_id_key, token_category_key=None, token_tokenid_key=None, token_decimals_key=None):
    """
    Expand token field from dictionary item with annotated token fields.
    
    Args:
        item: Dictionary from .values() query
        token_id_key: Key for token ID (e.g., '_token_id')
        token_category_key: Key for token category (for CashTokens, same as token_id)
        token_tokenid_key: Key for SLP tokenid (for SLP tokens)
        token_decimals_key: Key for token decimals
    """
    token_id = item.pop(token_id_key)
    token_decimals = item.pop(token_decimals_key) if token_decimals_key else None
    
    if token_category_key:
        # CashToken (NFT or FT)
        token_category = item.pop(token_category_key)
        item['token'] = {
            'id': token_id,
            'asset_id': f"ct/{token_category}",
            'decimals': token_decimals if token_decimals is not None else 0
        }
    elif token_tokenid_key:
        # SLP Token
        token_tokenid = item.pop(token_tokenid_key)
        item['token'] = {
            'id': token_id,
            'asset_id': f"slp/{token_tokenid}" if token_tokenid else None,
            'decimals': token_decimals if token_decimals is not None else 0
        }


def store_object(key, obj, cache):
    """Serialize an object using pickle and store it in Redis as a string."""
    # Serialize the object to binary
    pickled_data = pickle.dumps(obj)
    # Convert binary to Base64 string
    encoded_data = base64.b64encode(pickled_data).decode('utf-8')
    # Store in Redis
    cache.set(key, encoded_data, ex=60 * 5)  # Cache for 5 minutes


def retrieve_object(key, cache):
    """Retrieve an object from Redis and deserialize it using pickle."""
    # Get the Base64 string from Redis
    encoded_data = cache.get(key)
    if encoded_data is None:
        return None
    # Convert Base64 string back to binary
    pickled_data = base64.b64decode(encoded_data)
    # Deserialize the binary back to an object
    return pickle.loads(pickled_data)


class ContractHistoryView(APIView):

    @swagger_auto_schema(
        responses={200: PaginatedWalletHistorySerializer},
        manual_parameters=[
            openapi.Parameter(name="page", type=openapi.TYPE_NUMBER, in_=openapi.IN_QUERY, default=1),
            openapi.Parameter(name="type", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, default="all", enum=["incoming", "outgoing"]),
            openapi.Parameter(name="txids", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, required=False),
        ]
    )
    def get(self, request, *args, **kwargs):
        address = kwargs.get('address', None)
        page = request.query_params.get('page', 1)
        record_type = request.query_params.get('type', 'all')
        txids = request.query_params.get("txids", "")

        if isinstance(txids, str):
            txids = [txid for txid in txids.split(",") if txid]
        
        data = None
        history = []
        
        try:
            address = Address.objects.get(address=address)
        except Address.DoesNotExist:
            return Response(data={'error': 'Address not found'}, status=status.HTTP_404_NOT_FOUND)
        qs = ContractHistory.objects.exclude(amount=0)
        qs = qs.filter(address=address)

        if record_type in ['incoming', 'outgoing']:
            qs = qs.filter(record_type=record_type)
        if len(txids):
            qs = qs.filter(txid__in=txids)

        qs = qs.order_by(F('tx_timestamp').desc(nulls_last=True), F('date_created').desc(nulls_last=True))
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
        )

        pages = Paginator(history, 10)
        page_obj = pages.page(int(page))
        data = {
            'history': page_obj.object_list,
            'page': page,
            'num_pages': pages.num_pages,
            'has_next': page_obj.has_next()
        }
        return Response(data=data, status=status.HTTP_200_OK)


class WalletHistoryView(APIView):

    @swagger_auto_schema(
        responses={200: PaginatedWalletHistorySerializer},
        manual_parameters=[
            openapi.Parameter(name="page", type=openapi.TYPE_NUMBER, in_=openapi.IN_QUERY, default=1),
            openapi.Parameter(name="page_size", type=openapi.TYPE_NUMBER, in_=openapi.IN_QUERY, default=10),
            openapi.Parameter(name="posid", type=openapi.TYPE_NUMBER, in_=openapi.IN_QUERY, required=False),
            openapi.Parameter(name="type", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, default="all", enum=["incoming", "outgoing"]),
            openapi.Parameter(name="txids", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, required=False),
            openapi.Parameter(name="reference", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, required=False),
            openapi.Parameter(name="exclude_attr", type=openapi.TYPE_BOOLEAN, in_=openapi.IN_QUERY, default=True, required=False),
            openapi.Parameter(name="attribute", type=openapi.TYPE_STRING, in_=openapi.IN_QUERY, required=False),
        ]
    )
    def get(self, request, *args, **kwargs):
        wallet_hash = kwargs.get('wallethash', None)
        token_id_or_category = kwargs.get('tokenid_or_category', None)
        category = kwargs.get('category', None)
        index = kwargs.get('index', None)
        txid = kwargs.get('txid', None)
        page = request.query_params.get('page', 1)
        page_size = request.query_params.get('page_size', 10)
        record_type = request.query_params.get('type', 'all')
        posid = request.query_params.get("posid", None)
        txids = request.query_params.get("txids", "")
        reference = request.query_params.get("reference", "")
        attribute = request.query_params.get("attribute", "")
        include_attrs = str(request.query_params.get("exclude_attr", "true")).strip().lower() == "true"
        
        is_cashtoken_nft = False
        if index and txid:
            try:
                index = int(index)
                is_cashtoken_nft = True
            except (TypeError, ValueError):
                return Response(data={'error': f'invalid index: {index}'}, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(txids, str):
            txids = [txid for txid in txids.split(",") if txid]

        try:
            wallet = Wallet.objects.get(wallet_hash=wallet_hash)
        except Wallet.DoesNotExist:
            return Response(data={'error': 'Wallet not found'}, status=status.HTTP_404_NOT_FOUND)

        cache_key = None
        history = []
        data = None
        use_cache = record_type == 'all' and not index and not txids and not reference and not attribute
        
        if wallet.version > 1:
            if use_cache:
                cache = settings.REDISKV
                # Include page_size and token_id_or_category in cache key to avoid collisions
                token_key = token_id_or_category or category or 'bch'
                cache_key = f'wallet:history:{wallet_hash}:{token_key}:{str(page)}:{str(page_size)}'
                data = retrieve_object(cache_key, cache)

        if not data:
            qs = WalletHistory.objects.exclude(amount=0)

            if attribute:
                meta_attributes = TransactionMetaAttribute.objects.filter(wallet_hash=wallet_hash, value=attribute)
                wallet_txids_with_attrs = meta_attributes.values('txid').distinct('txid')
                qs = qs.filter(txid__in=wallet_txids_with_attrs)

            if posid:
                try:
                    posid = int(posid)
                except (TypeError, ValueError):
                    return Response(data=[f"invalid POS ID: {type(posid)}({posid})"], status=status.HTTP_400_BAD_REQUEST)
                    
                qs = qs.filter_pos(wallet_hash, posid)
            else:
                qs = qs.filter(wallet=wallet)

            if record_type in ['incoming', 'outgoing']:
                qs = qs.filter(record_type=record_type)
            if len(txids):
                qs = qs.filter(txid__in=txids)
            if reference:
                qs = qs.filter(txid__startswith=reference.lower())

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
                        ).select_related('cashtoken_nft', 'cashtoken_nft__info')
                        history = qs.annotate(
                            _token=F('cashtoken_nft__category')
                        )
                    else:
                        qs = qs.filter(cashtoken_ft__category=token_id_or_category).select_related('cashtoken_ft', 'cashtoken_ft__info')
                        history = qs.annotate(
                            _token=F('cashtoken_ft__category'),
                            amount=ExpressionWrapper(
                                #F('amount') / (10 ** F('cashtoken_ft__info__decimals')),
                                F('amount'),
                                output_field=FloatField()
                            )
                        )

                    memo_subquery = get_memo_subquery(wallet_hash)
                    
                    if is_cashtoken_nft:
                        history = history.annotate(
                            encrypted_memo=Subquery(memo_subquery),
                            _token_id=F('cashtoken_nft__category'),
                            _token_category=F('cashtoken_nft__category'),
                            _token_decimals=F('cashtoken_nft__info__decimals')
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
                            'encrypted_memo',
                            '_token_id',
                            '_token_category',
                            '_token_decimals',
                        )
                    else:
                        history = history.annotate(
                            encrypted_memo=Subquery(memo_subquery),
                            _token_id=F('cashtoken_ft__category'),
                            _token_category=F('cashtoken_ft__category'),
                            _token_decimals=F('cashtoken_ft__info__decimals')
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
                            'encrypted_memo',
                            '_token_id',
                            '_token_category',
                            '_token_decimals',
                        )
                    
                    # Post-process to expand token field
                    history = list(history)
                    for item in history:
                        expand_token_from_dict(
                            item,
                            token_id_key='_token_id',
                            token_category_key='_token_category',
                            token_decimals_key='_token_decimals'
                        )
                    
                    # Add fiat_amounts from computed property
                    # Collect unique txids to fetch WalletHistory objects efficiently
                    history_txids = {item['txid'] for item in history}
                    wallet_histories_list = list(WalletHistory.objects.filter(
                        txid__in=history_txids,
                        wallet=wallet
                    ).select_related('wallet', 'token'))
                    
                    # Create a lookup dict - use (txid, record_type, wallet_id) as key since amounts might have precision differences
                    wallet_histories_lookup = {}
                    for h in wallet_histories_list:
                        # Primary key: (txid, record_type, wallet_id)
                        key = (h.txid, h.record_type, h.wallet_id)
                        if key not in wallet_histories_lookup:
                            wallet_histories_lookup[key] = h
                    
                    # Add fiat_amounts to each item
                    for item in history:
                        key = (item['txid'], item['record_type'], wallet.id)
                        if key in wallet_histories_lookup:
                            wallet_history_obj = wallet_histories_lookup[key]
                            # Get fiat_amounts from the computed property
                            item['fiat_amounts'] = wallet_history_obj.fiat_amounts
                        else:
                            item['fiat_amounts'] = None
                else:
                    memo_subquery = get_memo_subquery(wallet_hash)
                    
                    qs = qs.filter(token__tokenid=token_id_or_category).select_related('token')

                    history = qs.annotate(
                        _token=F('token__tokenid'),
                        encrypted_memo=Subquery(memo_subquery),
                        _token_id=F('token__id'),
                        _token_tokenid=F('token__tokenid'),
                        _token_decimals=F('token__decimals')
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
                        'encrypted_memo',
                        '_token_id',
                        '_token_tokenid',
                        '_token_decimals',
                    )
                    
                    # Post-process to expand token field
                    history = list(history)
                    for item in history:
                        expand_token_from_dict(
                            item,
                            token_id_key='_token_id',
                            token_tokenid_key='_token_tokenid',
                            token_decimals_key='_token_decimals'
                        )
                    
                    # Add fiat_amounts from computed property
                    # Collect unique txids to fetch WalletHistory objects efficiently
                    history_txids = {item['txid'] for item in history}
                    wallet_histories_list = list(WalletHistory.objects.filter(
                        txid__in=history_txids,
                        wallet=wallet
                    ).select_related('wallet', 'token'))
                    
                    # Create a lookup dict - use (txid, record_type, wallet_id) as key since amounts might have precision differences
                    wallet_histories_lookup = {}
                    for h in wallet_histories_list:
                        # Primary key: (txid, record_type, wallet_id)
                        key = (h.txid, h.record_type, h.wallet_id)
                        if key not in wallet_histories_lookup:
                            wallet_histories_lookup[key] = h
                    
                    # Add fiat_amounts to each item
                    for item in history:
                        key = (item['txid'], item['record_type'], wallet.id)
                        if key in wallet_histories_lookup:
                            wallet_history_obj = wallet_histories_lookup[key]
                            # Get fiat_amounts from the computed property
                            item['fiat_amounts'] = wallet_history_obj.fiat_amounts
                        else:
                            item['fiat_amounts'] = None
            else:
                memo_subquery = get_memo_subquery(wallet_hash)
                
                qs = qs.filter(token__name='bch').select_related('token')
                history = qs.annotate(
                    encrypted_memo=Subquery(memo_subquery),
                    _token_id=F('token__id'),
                    _token_tokenid=F('token__tokenid'),
                    _token_decimals=F('token__decimals')
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
                    'encrypted_memo',
                    '_token_id',
                    '_token_tokenid',
                    '_token_decimals',
                )
                
                # Post-process to expand token field
                history = list(history)
                for item in history:
                    expand_token_from_dict(
                        item,
                        token_id_key='_token_id',
                        token_tokenid_key='_token_tokenid',
                        token_decimals_key='_token_decimals'
                    )
                
                # Add fiat_amounts from computed property
                # Collect unique txids to fetch WalletHistory objects efficiently
                history_txids = {item['txid'] for item in history}
                wallet_histories_list = list(WalletHistory.objects.filter(
                    txid__in=history_txids,
                    wallet=wallet
                ).select_related('wallet', 'token'))
                
                # Create a lookup dict - use (txid, record_type, wallet_id) as key since amounts might have precision differences
                # For outgoing transactions, amounts are stored as negative in DB, but we'll match by record_type
                wallet_histories_lookup = {}
                for h in wallet_histories_list:
                    # Primary key: (txid, record_type, wallet_id)
                    key = (h.txid, h.record_type, h.wallet_id)
                    # If multiple records exist for same key, prefer the one that matches the amount
                    if key not in wallet_histories_lookup:
                        wallet_histories_lookup[key] = h
                    else:
                        # If we already have one, keep the first match (they should be the same anyway)
                        pass
                
                # Add fiat_amounts to each item
                for item in history:
                    key = (item['txid'], item['record_type'], wallet.id)
                    if key in wallet_histories_lookup:
                        wallet_history_obj = wallet_histories_lookup[key]
                        # Get fiat_amounts from the computed property
                        item['fiat_amounts'] = wallet_history_obj.fiat_amounts
                    else:
                        item['fiat_amounts'] = None

            if wallet.version == 1:
                return Response(data=history, status=status.HTTP_200_OK)
            else:
                pages = Paginator(history, page_size)
                page_obj = pages.page(int(page))
                data = {
                    'history': page_obj.object_list,
                    'page': page,
                    'num_pages': pages.num_pages,
                    'has_next': page_obj.has_next()
                }

                if use_cache:
                    store_object(cache_key, data, cache)

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
