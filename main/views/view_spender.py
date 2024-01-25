from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from main.models import Transaction
import json


class SpenderTransactionView(View):

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super(SpenderTransactionView, self).dispatch(request, *args, **kwargs)

    def post(self, request):
        data = json.loads(request.body)
        response = {'tx_found': False}
        txn_check = Transaction.objects.filter(txid=data['txid'], index=data['index'])
        if txn_check.exists():
            response = {'tx_found': True, 'spent': False}
            txn = txn_check.first()
            if txn.spent:
                response['spent'] = True
                response['spender'] = txn.spending_txid
        return JsonResponse(response)
