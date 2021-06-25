from main.models import Transaction, Wallet
from django.db.models import Q, Sum, F
from django.db.models.functions import Coalesce
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from main import serializers


def _get_slp_balance(query):
    qs = Transaction.objects.filter(query)
    qs_balance = qs.annotate(
        tokenid=F('token__tokenid'),
        token_name=F('token__name'),
        token_ticker=F('token__token_ticker'),
        token_type=F('token__token_type')
    ).values(
        'tokenid',
        'token_name',
        'token_ticker',
        'token_type'
    ).order_by(
        'tokenid'
    ).annotate(
        balance=Coalesce(Sum('amount'), 0)
    )
    return qs_balance


def _get_bch_balance(query):
    # Exclude dust amounts as they're likely to be SLP transactions
    # TODO: Needs another more sure way to exclude SLP transactions
    dust = 546 / (10 ** 8)
    query = query & Q(amount__gt=dust)
    qs = Transaction.objects.filter(query)
    qs_balance = qs.aggregate(
        balance=Coalesce(Sum('amount'), 0)
    )
    return qs_balance

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
                query = Q(address__address=data['address']) & Q(spent=False) & Q(token__tokenid=tokenid)
            else:
                query =  Q(address__address=data['address']) & Q(spent=False)
            qs_balance = _get_slp_balance(query)
            data['balance'] = list(qs_balance)
            data['valid'] = True
        
        if bchaddress.startswith('bitcoincash:'):
            data['address'] = bchaddress
            query = Q(address__address=data['address']) & Q(spent=False)
            qs_balance = _get_bch_balance(query)
            data['balance'] = qs_balance['balance']
            data['valid'] = True

        if wallet_hash:
            wallet = Wallet.objects.get(wallet_hash=wallet_hash)
            data['wallet'] = wallet_hash

            if wallet.wallet_type == 'slp':
                if tokenid:
                    query = Q(wallet=wallet) & Q(spent=False) & Q(token__tokenid=tokenid)
                else:
                    query =  Q(wallet=wallet) & Q(spent=False)
                qs_balance = _get_slp_balance(query)
                data['balance'] = list(qs_balance)
                data['valid'] = True

            elif wallet.wallet_type == 'bch':
                query = Q(wallet=wallet) & Q(spent=False)
                qs_balance = _get_bch_balance(query)
                data['balance'] = qs_balance['balance']
                data['valid'] = True

        return Response(data=data, status=status.HTTP_200_OK)
