from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import F, Q, Subquery, Func, OuterRef
from rest_framework import status
from main.models import Wallet, Address, WalletHistory
from django.core.paginator import Paginator

POS_ID_MAX_DIGITS = 4

class WalletHistoryView(APIView):

    def get(self, request, *args, **kwargs):
        wallet_hash = kwargs.get('wallethash', None)
        token_id = kwargs.get('tokenid', None)
        page = request.query_params.get('page', 1)
        record_type = request.query_params.get('type', 'all')
        posid = request.query_params.get("posid", None)

        qs = WalletHistory.objects.filter(wallet__wallet_hash=wallet_hash)
        if record_type in ['incoming', 'outgoing']:
            qs = qs.filter(record_type=record_type)

        if posid:
            try:
                posid = int(posid)
                posid = str(posid)
                pad = "0" * (len(posid)-POS_ID_MAX_DIGITS)
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
