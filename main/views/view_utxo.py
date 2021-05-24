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
    
        if slpaddress.startswith('simpleledger:'):
            data['address'] = slpaddress
            if tokenid:
                query = Q(address=data['address']) & Q(spent=False) & Q(token__tokenid=tokenid)
            else:
                query =  Q(address=data['address']) & Q(spent=False)
                
            qs = Transaction.objects.filter(query)
        
        if bchaddress.startswith('bitcoincash:'):
            data['address'] = bchaddress
            qs = Transaction.objects.filter(Q(address=data['address']) & Q(spent=False))
                   
        if qs:
            utxos_values = qs.annotate(
                token_name=F('token__name'),
                block=F('blockheight__number'),
                unspent_index=F('index'),
                tokenid=F('token__tokenid')
            ).values('txid', 'amount', 'tokenid', 'token_name', 'unspent_index', 'block')

            data['utxos'] = list(utxos_values)
            data['valid'] = True        
        return Response(data=data, status=status.HTTP_200_OK)
