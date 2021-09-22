from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import F
from rest_framework import status
from main.models import Token, WalletHistory, Token
from main.tasks import get_token_meta_data



class TokensView(APIView):

    def get(self, request, *args, **kwargs):
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
        return Response(data)


class WalletTokensView(APIView):

    def get(self, request, *args, **kwargs):
        wallet_hash = kwargs.get('wallethash', None)
        qs = WalletHistory.objects.filter(
            wallet__wallet_hash=wallet_hash
        )
        token_type = request.query_params.get('token_type', None)
        if token_type:
            qs = qs.filter(token__token_type=token_type)
        qs = qs.order_by(
            'token'
        ).distinct(
            'token'
        )
        tokens = qs.annotate(
            _token=F('token__tokenid'),
            name=F('token__name'),
            symbol=F('token__token_ticker'),
            type=F('token__token_type'),
            image_url=F('token__image_url'),
            thumbnail_image_url=F('token__thumbnail_image_url')
        ).rename_annotations(
            _token='token_id'
        ).values(
            'token_id',
            'name',
            'symbol',
            'type',
            'image_url',
            'thumbnail_image_url'
        )
        return Response(data=tokens, status=status.HTTP_200_OK)
