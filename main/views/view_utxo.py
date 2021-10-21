from rest_framework.views import APIView
from main.models import Transaction, Wallet, Token
from main.tasks import get_token_meta_data
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q, F, Func


class Round(Func):
    function = "ROUND"
    template = "%(function)s(%(expressions)s::numeric, 0)"


def _get_slp_utxos(query, show_address_index=False):
    qs = Transaction.objects.filter(query)
    if show_address_index:
        utxos_values = qs.annotate(
            vout=F('index'),
            tokenid=F('token__tokenid'),
            token_name=F('token__name'),
            decimals=F('token__decimals'),
            token_ticker=F('token__token_ticker'),
            token_type=F('token__token_type'),
            block=F('blockheight__number'),
            wallet_index=F('address__wallet_index'),
            address_path=F('address__address_path')
        ).values(
            'txid',
            'vout',
            'amount',
            'tokenid',
            'token_name',
            'token_ticker',
            'decimals',
            'token_type',
            'block',
            'wallet_index',
            'address_path'
        )
    else:
        utxos_values = qs.annotate(
            vout=F('index'),
            tokenid=F('token__tokenid'),
            token_name=F('token__name'),
            decimals=F('token__decimals'),
            token_ticker=F('token__token_ticker'),
            token_type=F('token__token_type'),
            block=F('blockheight__number'),
        ).values(
            'txid',
            'vout',
            'amount',
            'tokenid',
            'token_name',
            'token_ticker',
            'decimals',
            'token_type',
            'block'
        )
    return utxos_values


def _get_bch_utxos(query, show_address_index=False):
    # Exclude dust amounts as they're likely to be SLP transactions
    # TODO: Needs another more sure way to exclude SLP transactions
    dust = 546 / (10 ** 8)
    query = query & Q(amount__gt=dust)
    qs = Transaction.objects.filter(query)
    if show_address_index:
        utxos_values = qs.annotate(
            value=Round(F('amount') * (10 ** 8)),
            vout=F('index'),
            block=F('blockheight__number'),
            wallet_index=F('address__wallet_index'),
            address_path=F('address__address_path')
        ).values(
            'txid',
            'vout',
            'value',
            'block',
            'wallet_index',
            'address_path'
        )
    else:
        utxos_values = qs.annotate(
            value=Round(F('amount') * (10 ** 8)),
            vout=F('index'),
            block=F('blockheight__number'),
        ).values(
            'txid',
            'vout',
            'value',
            'block'
        )
    return utxos_values


class UTXO(APIView):

    def get(self, request, *args, **kwargs):

        slpaddress = kwargs.get('slpaddress', '')
        bchaddress = kwargs.get('bchaddress', '')
        tokenid = kwargs.get('tokenid', '')
        wallet_hash = kwargs.get('wallethash', '')

        data = { 'valid': False }
        qs = None
        
        if bchaddress.startswith('bitcoincash:'):
            data['address'] = bchaddress
            query = Q(address__address=data['address']) & Q(spent=False)
            utxos_values = _get_bch_utxos(query)
        
        if slpaddress.startswith('simpleledger:'):
            data['address'] = slpaddress
            if tokenid:
                query = Q(address__address=data['address']) & Q(spent=False) & Q(token__tokenid=tokenid)
            else:
                query =  Q(address__address=data['address']) & Q(spent=False)
            utxos_values = _get_slp_utxos(query)

        if wallet_hash:
            wallet = Wallet.objects.get(wallet_hash=wallet_hash)
            data['wallet'] = wallet_hash
            
            if wallet.wallet_type == 'slp':
                if tokenid:
                    query = Q(wallet=wallet) & Q(spent=False) & Q(token__tokenid=tokenid)
                else:
                    query =  Q(wallet=wallet) & Q(spent=False)
                utxos_values = _get_slp_utxos(query, show_address_index=True)

            elif wallet.wallet_type == 'bch':
                query = Q(wallet=wallet) & Q(spent=False)
                utxos_values = _get_bch_utxos(query, show_address_index=True)

        data['utxos'] = list(utxos_values)
        data['valid'] = True  
        return Response(data=data, status=status.HTTP_200_OK)
