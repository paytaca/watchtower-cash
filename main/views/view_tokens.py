from rest_framework import viewsets, mixins
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import F
from rest_framework import status

from main.filters import TokensViewSetFilter
from main.models import (
    Token,
    WalletHistory,
    Token,
    WalletNftToken
)
from main.serializers import TokenSerializer
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
        return Response(serializer=serializer.data)


class WalletTokensView(APIView):

    def get(self, request, *args, **kwargs):
        wallet_hash = kwargs.get('wallethash', None)
        token_type = request.query_params.get('token_type', None)
        qs = WalletHistory.objects.filter(
            wallet__wallet_hash=wallet_hash
        )
        tokens = {}
        if token_type:
            if int(token_type) == 65:
                qs = WalletNftToken.objects.filter(
                    wallet__wallet_hash=wallet_hash,
                    date_dispensed__isnull=True
                )
                qs = qs.order_by(
                    'token',
                    '-date_acquired'
                ).distinct(
                    'token'
                )
                tokens = qs.annotate(
                    _token=F('token__tokenid'),
                    name=F('token__name'),
                    symbol=F('token__token_ticker'),
                    type=F('token__token_type'),
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
                    'original_image_url',
                    'medium_image_url',
                    'thumbnail_image_url',
                    'txid',
                    'date_acquired'
                )
        return Response(data=tokens, status=status.HTTP_200_OK)
