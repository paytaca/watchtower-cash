from rest_framework.views import APIView
from main.models import Transaction
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q, F

class UTXO(APIView):

    def get(self, request, *args, **kwargs):

        slpaddress = kwargs.get('slpaddress', '')
        bchaddress = kwargs.get('bchaddress', '')
        tokenid = kwargs.get('tokenid', '')

        data = { 'valid': False }
        qs = None
        
        if bchaddress.startswith('bitcoincash:'):
            data['address'] = bchaddress
            # Exclude dust amounts as they're likely to be SLP transactions
            # TODO: Needs another more sure way to exclude SLP transactions
            dust = 546 / (10 ** 8)
            query = Q(address=data['address']) & Q(spent=False) & Q(amount__gt=dust)
            qs = Transaction.objects.filter(query)
            utxos_values = qs.annotate(
                value=F('amount') * (10 ** 8),
                vout=F('index'),
                block=F('blockheight__number'),
            ).values(
                'txid',
                'vout',
                'value',
                'block'
            )
        
        if slpaddress.startswith('simpleledger:'):
            data['address'] = slpaddress
            if tokenid:
                query = Q(address=data['address']) & Q(spent=False) & Q(token__tokenid=tokenid)
            else:
                query =  Q(address=data['address']) & Q(spent=False)
                
            qs = Transaction.objects.filter(query)
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

        data['utxos'] = list(utxos_values)
        data['valid'] = True  
        return Response(data=data, status=status.HTTP_200_OK)
