from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import F
from rest_framework import status
from main.models import Wallet, WalletHistory


class WalletHistoryView(APIView):

    def get(self, request, *args, **kwargs):
        wallet_hash = kwargs.get('wallethash', None)
        token_id = kwargs.get('tokenid', None)
        qs = WalletHistory.objects.filter(wallet__wallet_hash=wallet_hash)
        wallet = Wallet.objects.get(wallet_hash=wallet_hash)
        if wallet.wallet_type == 'slp':
            qs = qs.filter(token__tokenid=token_id)
            data = qs.annotate(
                _token=F('token__tokenid')
            ).rename_annotations(
                _token='token_id'
            ).values(
                'record_type',
                'txid',
                'amount',
                'token',
                'date_created'
            )
        elif wallet.wallet_type == 'bch':
            data = qs.values(
                'record_type',
                'txid',
                'amount',
                'date_created'
            )
        return Response(data=data, status=status.HTTP_200_OK)
