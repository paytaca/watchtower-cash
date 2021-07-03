from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import F
from rest_framework import status
from main.models import Token, WalletHistory


class TokensView(APIView):

    def get(self, request, *args, **kwargs):
        wallet_hash = kwargs.get('wallethash', None)
        qs = WalletHistory.objects.filter(
            wallet__wallet_hash=wallet_hash
        ).distinct('token')
        tokens = qs.annotate(
            _token=F('token__tokenid'),
            name=F('token__name'),
            symbol=F('token__token_ticker'),
            type=F('token__token_type'),
        ).rename_annotations(
            _token='token_id'
        ).values(
            'token_id',
            'name',
            'symbol',
            'type',
            'logo_url'
        )
        return Response(data=tokens, status=status.HTTP_200_OK)
