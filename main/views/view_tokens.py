from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

from django.db.models import F, Subquery, OuterRef, Count, Q
from django.conf import settings

from rest_framework import viewsets, mixins
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from main.filters import TokensViewSetFilter
from main.models import (
    Token,
    WalletHistory,
    Token,
    WalletNftToken
)
from main.serializers import TokenSerializer, WalletTokenSerializer
from main.tasks import get_token_meta_data

from smartbch.pagination import CustomLimitOffsetPagination


class TokensViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin
):
    lookup_field="tokenid"
    serializer_class = TokenSerializer
    pagination_class = CustomLimitOffsetPagination

    filter_backends = [
        TokensViewSetFilter,
    ]

    def get_queryset(self):
        return Token.objects.exclude(
            tokenid=settings.WT_DEFAULT_CASHTOKEN_ID
        )

    def retrieve(self, request, *args, **kwargs):
        token_id = kwargs.get('tokenid', None)
        token_check = Token.objects.filter(tokenid=token_id)
        data = None
        if token_check.exists():
            token = token_check.first()
            data = token.get_info()
        else:
            data = get_token_meta_data.run(token_id)
        if data:
            data['success'] = True
        else:
            data['success'] = False
            data['error'] = 'invalid_token_id'
        serializer = self.serializer_class(data=data)
        return Response(data=serializer.initial_data)


class SlpFungibleTokensViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    """
    List/retrieve fungible SLP tokens, optionally scoped by wallet/address.
    Mirrors `/api/cashtokens/fungible/` response shape and favorites ordering behavior.
    """

    lookup_field = "tokenid"
    serializer_class = None  # set below (avoids circular import ordering in module)
    pagination_class = CustomLimitOffsetPagination

    filter_backends = [
        TokensViewSetFilter,
    ]

    def get_queryset(self):
        # Fungible SLP tokens are token_type=1. Exclude the internal CashToken placeholder token.
        # Also exclude NFT1 "special NFTs" that can appear as token_type=1 (decimals==0 and mint_amount==1).
        #
        # Additionally, exclude the DB "bch" token row (it can have token_type=1 but an empty tokenid),
        # by only allowing real SLP tokenids (64-hex).
        return Token.objects.filter(
            token_type=1,
            # Use iregex to support stored uppercase tokenids too.
            tokenid__iregex=r"^[0-9a-f]{64}$",
        ).exclude(
            tokenid=settings.WT_DEFAULT_CASHTOKEN_ID
        ).exclude(
            decimals=0,
            mint_amount=1,
        )

    def get_serializer_class(self):
        # Local import to avoid import cycles at module import time
        from main.serializers import SlpFungibleTokenSerializer

        return SlpFungibleTokenSerializer

    def get_serializer_context(self):
        """
        Add wallet_hash to serializer context so balance + favorites can be calculated.
        """
        context = super().get_serializer_context()
        wallet_hash = self.request.query_params.get("wallet_hash", None)
        if wallet_hash:
            context["wallet_hash"] = wallet_hash
        return context

    def list(self, request, *args, **kwargs):
        """
        Override list to order by favorites and favorite_order.
        Supports favorites_only query parameter to filter only favorited tokens.
        """
        queryset = self.filter_queryset(self.get_queryset())

        wallet_hash = request.query_params.get("wallet_hash", None)
        favorites_only = request.query_params.get("favorites_only", "").lower() == "true"

        if favorites_only and not wallet_hash:
            from rest_framework import status
            return Response(
                {"error": "wallet_hash is required when favorites_only=true"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if wallet_hash:
            from main.models import AssetSetting

            try:
                asset_setting = AssetSetting.objects.only("favorites").get(wallet_hash=wallet_hash)
                favorites = asset_setting.favorites

                if not isinstance(favorites, list):
                    favorites = []
                if len(favorites) == 0:
                    favorites = None
            except AssetSetting.DoesNotExist:
                favorites = None

            if favorites is not None and not isinstance(favorites, list):
                favorites = None

            # Build a lookup of favorited item IDs -> favorite order (among favorite=1 items).
            favorite_order_map = {}
            if favorites:
                order = 0
                for item in favorites:
                    if not isinstance(item, dict):
                        continue
                    item_id = item.get("id")
                    if not item_id:
                        continue
                    favorite_value = item.get("favorite", 0)
                    if not isinstance(favorite_value, int):
                        try:
                            favorite_value = int(favorite_value)
                        except (ValueError, TypeError):
                            favorite_value = 0
                    if favorite_value == 1:
                        normalized_id = str(item_id).strip()
                        if normalized_id and normalized_id not in favorite_order_map:
                            favorite_order_map[normalized_id] = order
                            order += 1

            def is_token_favorited(obj: Token) -> bool:
                if not favorite_order_map:
                    return False
                # Favorites IDs are expected to be `slp/<tokenid>`; also accept raw tokenid for compatibility.
                return (obj.info_id in favorite_order_map) or (obj.tokenid in favorite_order_map)

            if favorites_only:
                queryset = [obj for obj in queryset if is_token_favorited(obj)]
            else:
                queryset = list(queryset)

            def get_favorite_info(obj: Token):
                if not favorite_order_map:
                    return (True, float("inf"))
                order = favorite_order_map.get(obj.info_id)
                if order is None:
                    order = favorite_order_map.get(obj.tokenid)
                if order is None:
                    return (True, float("inf"))
                return (False, order)

            queryset.sort(key=get_favorite_info)

            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

        # No wallet_hash: use default pagination behavior (and disallow favorites_only).
        if favorites_only:
            from rest_framework import status
            return Response(
                {"error": "wallet_hash is required when favorites_only=true"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class WalletTokensView(APIView):

    @swagger_auto_schema(
        responses={200: WalletTokenSerializer(many=True)},
        manual_parameters=[
            openapi.Parameter(
                name="token_type", type=openapi.TYPE_NUMBER,
                in_=openapi.IN_QUERY, enum=[65, 129]
            ),
            openapi.Parameter(
                name="nft_token_group", type=openapi.TYPE_STRING,
                in_=openapi.IN_QUERY, required=False,
                description="filter tokens by nft group for token_type=65." \
                            "set 'ungrouped' simple nfts or nft1 with unknown groups",
            ),
        ]
    )
    def get(self, request, *args, **kwargs):
        wallet_hash = kwargs.get('wallethash', None)
        token_type = request.query_params.get('token_type', None)
        nft_token_group = request.query_params.get('nft_token_group', None)
        try:
            token_type = int(token_type)
        except (ValueError, TypeError):
            token_type = None

        tokens = {
            "token_type": token_type,
            "wallet_hash": wallet_hash,
        }
        if token_type == 65:
            tokens = self.get_nfts(wallet_hash, nft_token_group=nft_token_group)
        elif token_type == 129:
            tokens = self.get_nft_groups(wallet_hash)
        return Response(data=tokens, status=status.HTTP_200_OK)

    def get_nfts(self, wallet_hash, nft_token_group=None):
        qs = WalletNftToken.objects.filter(
            wallet__wallet_hash=wallet_hash,
            date_dispensed__isnull=True
        )

        if nft_token_group:
            if nft_token_group == "ungrouped":
                qs = qs.filter(token__nft_token_group__isnull=True)
            else:
                qs = qs.filter(token__nft_token_group__tokenid=nft_token_group)

        qs = qs.order_by(
            'token',
            '-date_acquired'
        ).distinct(
            'token'
        )

        tokens_info = qs.annotate(
            _token=F('token__tokenid'),
            name=F('token__name'),
            symbol=F('token__token_ticker'),
            type=F('token__token_type'),
            nft_token_group=F('token__nft_token_group__tokenid'),
            original_image_url=F('token__original_image_url'),
            txid = F('acquisition_transaction__txid'),
            medium_image_url=F('token__medium_image_url'),
            thumbnail_image_url=F('token__thumbnail_image_url')
        ).rename_annotations(
            _token='token_id'
        ).values(
            'token_id',
            'name',
            'symbol',
            'type',
            'nft_token_group',
            'original_image_url',
            'medium_image_url',
            'thumbnail_image_url',
            'txid',
            'date_acquired'
        )
        return tokens_info

    def get_nft_groups(self, wallet_hash):
        qs = WalletNftToken.objects.filter(wallet__wallet_hash=wallet_hash, date_dispensed__isnull=True)
        tokenids_subquery = Subquery(qs.values("token__tokenid").distinct())

        # nft groups
        nft_token_group = Token.objects.filter(
            children__tokenid__in=tokenids_subquery,
        ).distinct().annotate(
            count=Count("children")
        )

        # Captures nft type 1 but nft group is unsaved in db; or simple nfts
        ungrouped_tokens_count = Token.objects.filter(
            tokenid__in=tokenids_subquery,
            nft_token_group__isnull=True,
        ).count()

        token_groups_info = [
            *nft_token_group.annotate(
                _token=F('tokenid'),
                symbol=F('token_ticker'),
                type=F('token_type'),
            ).rename_annotations(
                _token='token_id',
            ).values(
                'token_id',
                'name',
                'symbol',
                'type',
                'original_image_url',
                'medium_image_url',
                'thumbnail_image_url',
                'count',
            )
        ]

        if ungrouped_tokens_count:
            token_groups_info.append(dict(
                ungrouped_tokens=True,
                token_id="",
                name="Ungrouped",
                symbol="",
                type=None,
                original_image_url="",
                medium_image_url="",
                thumbnail_image_url="",
                count=ungrouped_tokens_count,
            ))
        return token_groups_info
