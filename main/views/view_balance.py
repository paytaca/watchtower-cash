from main.models import Transaction
from django.db.models import Q, Sum
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from main import serializers

class Balance(APIView):
    
    def get(self, request, *args, **kwargs):
        slpaddress = kwargs.get('slpaddress', '')
        bchaddress = kwargs.get('bchaddress', '')
        tokenid = kwargs.get('tokenid', '')

        data = { 'valid': False }
        balance = 0
        qs = None

        if slpaddress.startswith('simpleledger:'):
            data['address'] = slpaddress
            if tokenid:
                query = Q(address=data['address']) & Q(spent=False) & Q(token__tokenid=tokenid)
            else:
                query =  Q(address=data['address']) & Q(spent=False)
                
            qs = Transaction.objects.filter(query)
            qs_balance = qs.values('token__tokenid','token__name').order_by('token__tokenid').annotate(balance=Sum('amount'))
            data['balance'] = list(qs_balance)
            data['valid'] = True        
        
        if bchaddress.startswith('bitcoincash:'):
            data['address'] = bchaddress
            qs = Transaction.objects.filter(Q(address=data['address']) & Q(spent=False))
            qs_balance = qs.aggregate(balance=Sum('amount'))
            balance = qs_balance['balance']
            data['balance'] = balance
            data['valid'] = True        
        
        return Response(data=data, status=status.HTTP_200_OK)
        
