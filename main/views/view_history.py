from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import F
from rest_framework import status
from main.models import Wallet, WalletHistory
from django.core.paginator import Paginator


class WalletHistoryView(APIView):

    def get(self, request, *args, **kwargs):
        wallet_hash = kwargs.get('wallethash', None)
        token_id = kwargs.get('tokenid', None)
        page = request.GET.get('page', 1)
        record_type = request.GET.get('type', 'all')
        qs = WalletHistory.objects.filter(wallet__wallet_hash=wallet_hash)
        if record_type in ['incoming', 'outgoing']:
            qs = qs.filter(record_type=record_type)
        wallet = Wallet.objects.get(wallet_hash=wallet_hash)
        if wallet.wallet_type == 'slp':
            qs = qs.filter(token__tokenid=token_id)
            history = qs.annotate(
                _token=F('token__tokenid')
            ).rename_annotations(
                _token='token_id'
            ).values(
                'record_type',
                'txid',
                'amount',
                'token',
                'tx_fee',
                'senders',
                'recipients',
                'date_created'
            )
        elif wallet.wallet_type == 'bch':
            history = qs.values(
                'record_type',
                'txid',
                'amount',
                'tx_fee',
                'senders',
                'recipients',
                'date_created'
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
