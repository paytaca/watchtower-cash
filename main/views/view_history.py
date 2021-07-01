from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from main.models import WalletHistory


class WalletHistoryView(APIView):

    def get(self, request, *args, **kwargs):
        wallet_hash = kwargs.get('wallethash', None)
        qs = WalletHistory.objects.filter(wallet__wallet_hash=wallet_hash)
        data = qs.values(
            'record_type',
            'txid',
            'amount',
            'token',
            'date_created'
        )
        return Response(data=data, status=status.HTTP_200_OK)
