from main.models import Transaction, Wallet
from django.db.models import Q, Sum, F
from django.db.models.functions import Coalesce
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from main import serializers
from main.utils.tx_fee import get_tx_fee_bch


def _get_slp_balance(query, multiple_tokens=False):
    qs = Transaction.objects.filter(query)
    if multiple_tokens:
        # TODO: This is not working as expected in PostgresModel manager
        # I created a github issue for this here:
        # https://github.com/SectorLabs/django-postgres-extra/issues/143
        # Multiple tokens balance will be disabled til that issue is resolved
        qs_balance = qs.annotate(
            _token=F('token__tokenid'),
            token_name=F('token__name'),
            token_ticker=F('token__token_ticker'),
            token_type=F('token__token_type')
        ).rename_annotations(
            _token='token_id'
        ).values(
            'token_id',
            'token_name',
            'token_ticker',
            'token_type'
        ).annotate(
            balance=Coalesce(Sum('amount'), 0)
        )
    else:
        qs_balance = qs.aggregate(Sum('amount'))
    return qs_balance


def _get_bch_balance(query):
    # Exclude dust amounts as they're likely to be SLP transactions
    # TODO: Needs another more sure way to exclude SLP transactions
    dust = 546 / (10 ** 8)
    query = query & Q(amount__gt=dust)
    qs = Transaction.objects.filter(query)
    qs_count = qs.count()
    qs_balance = qs.aggregate(
        balance=Coalesce(Sum('amount'), 0)
    )
    return qs_balance, qs_count

class Balance(APIView):
    
    def get(self, request, *args, **kwargs):
        slpaddress = kwargs.get('slpaddress', '')
        bchaddress = kwargs.get('bchaddress', '')
        tokenid = kwargs.get('tokenid', '')
        wallet_hash = kwargs.get('wallethash', '')

        data = { 'valid': False }
        balance = 0
        qs = None

        if slpaddress.startswith('simpleledger:'):
            data['address'] = slpaddress
            if tokenid:
                multiple = False
                query = Q(address__address=data['address']) & Q(spent=False) & Q(token__tokenid=tokenid)
            else:
                multiple = True
                query =  Q(address__address=data['address']) & Q(spent=False)
            qs_balance = _get_slp_balance(query, multiple_tokens=multiple)
            data['balance'] = qs_balance['amount__sum'] or 0
            data['spendable'] = data['balance']
            data['valid'] = True
        
        if bchaddress.startswith('bitcoincash:'):
            data['address'] = bchaddress
            query = Q(address__address=data['address']) & Q(spent=False)
            qs_balance, qs_count = _get_bch_balance(query)
            bch_balance = qs_balance['balance'] or 0
            data['balance'] = round(bch_balance, 8)
            data['spendable'] = max(data['balance'] - get_tx_fee_bch(p2pkh_input_count=qs_count), 0)
            data['valid'] = True

        if wallet_hash:
            wallet = Wallet.objects.get(wallet_hash=wallet_hash)
            data['wallet'] = wallet_hash

            if wallet.wallet_type == 'slp':
                if tokenid:
                    multiple = False
                    query = Q(wallet=wallet) & Q(spent=False) & Q(token__tokenid=tokenid)
                else:
                    multiple = True
                    query =  Q(wallet=wallet) & Q(spent=False)
                qs_balance = _get_slp_balance(query, multiple_tokens=multiple)
                if multiple:
                    pass
                else:
                    data['balance'] = qs_balance['amount__sum'] or 0
                    data['spendable'] = data['balance']
                    data['token_id'] = tokenid
                    data['valid'] = True

            elif wallet.wallet_type == 'bch':
                query = Q(wallet=wallet) & Q(spent=False)
                qs_balance, qs_count = _get_bch_balance(query)
                data['balance'] = round(qs_balance['balance'], 8)
                data['spendable'] = max(data['balance'] - get_tx_fee_bch(p2pkh_input_count=qs_count), 0)
                data['valid'] = True

        return Response(data=data, status=status.HTTP_200_OK)
