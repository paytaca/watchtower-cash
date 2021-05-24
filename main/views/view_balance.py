from main.models import Transaction
from django.db.models import Q, Sum
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from main import serializers

class Balance(APIView):
    
    def get(self, request, *args, **kwargs):
        slpaddress = kwargs.get('slpaddress', None)
        bchaddress = kwargs.get('bchaddress', None)
        tokenid = kwargs.get('tokenid', None)

        data = { 'valid': False }
        balance = 0
        qs = None

        if slpaddress:
            if slpaddress.startswith('simpleledger:'):
                if tokenid:
                    data['tokenid'] = tokenid
                    data['address'] = slpaddress
                    qs = Transaction.objects.filter(
                        Q(address=data['address']) & Q(spent=False) & Q(token__tokenid=data['tokenid'])
                    )
        if bchaddress:
            if bchaddress.startswith('bitcoincash:'):
                data['address'] = bchaddress
                qs = Transaction.objects.filter(Q(address=data['address']) & Q(spent=False))
        if qs:
            qs_balance = qs.aggregate(balance=Sum('amount'))
            balance = qs_balance['balance']
            data['balance'] = balance
            data['valid'] = True        

        return Response(data=data, status=status.HTTP_200_OK)
        
