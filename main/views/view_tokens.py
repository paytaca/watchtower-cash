from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets, mixins
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import F, Subquery, OuterRef, Count, Q
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
        TokensViewSetFilter
    ]

    def get_queryset(self):
        return Token.objects.all()

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
                tokenid="ungrouped",
                name="Ungrouped",
                symbol="",
                type=None,
                original_image_url="",
                medium_image_url="",
                thumbnail_image_url="",
                count=ungrouped_tokens_count,
            ))
        return token_groups_info
