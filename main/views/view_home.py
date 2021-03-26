from rest_framework.viewsets import ViewSet
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.contrib.auth import authenticate, login, logout
from main.models import (
    Token as MyToken,
    Transaction,
    Subscription,    
    SlpAddress,
    BchAddress
)
from django.contrib.auth.models import User 
from django.urls import reverse
import json
from django.db.models import Q 
from operator import or_
from functools import reduce
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import authentication, permissions

class Home(ViewSet):
    
    def get(self, request):
        query = {}
        # if request.user.is_authenticated:
        #     token = request.GET.get('token', 'all')
        #     slpaddress = request.GET.get('slp', 'all')
        #     subscriber = Subscriber.objects.get(user=request.user)
        #     subscriptions = subscriber.subscription.all()
        #     new = True
        #     if not subscriptions.count():
        #         new = False
        #     subquery = []
        #     if token != 'all':
        #         subquery.append(Q(token__tokenid=token))

        #     if slpaddress != 'all':
        #         slpaddress = int(slpaddress)
        #         subquery.append(Q(slp__id=slpaddress))
        #     if subquery:
        #         mainquery = reduce(or_, subquery)
        #         subscriptions = subscriptions.filter(mainquery)

        #     transactions = Transaction.objects.all()
        #     subquery = []
        #     if token != 'all':
        #         ids = subscriptions.values('token__tokenid')
        #         tokens = MyToken.objects.filter(tokenid__in=ids).values_list('id', flat=True)
        #         subquery.append(Q(token__id__in=tokens))
        #     if slpaddress != 'all':
        #         trids = SlpAddress.objects.filter(id=slpaddress).values_list('transactions__id', flat=True)
        #         subquery.append(Q(id__in=trids))
        #     if subquery:
        #         mainquery = reduce(or_, subquery)
        #         transactions = transactions.filter(mainquery)
        #     transactions = transactions.order_by('-created_datetime')
        #     transactions = transactions.values(
        #         'id',
        #         'txid',
        #         'amount',
        #         'blockheight__number'
        #     )[0:100]
        #     subs = subscriber.subscription.all()
        #     slpaddresses = list(subs.values('slp__id', 'slp__address'))
        #     tokens = list(subs.values('token__tokenid', 'token__name'))
        #     slpaddresses.insert(0, {
        #         'slp__id': 'all',
        #         'slp__address': 'All SLP Addresses'
        #     })
        #     tokens.insert(0, {
        #         'token__tokenid': 'all',
        #         'token__name': 'All Tokens' 
        #     })
            
        #     return render(request, 'base/home.html', {
        #         "new": new,
        #         "transactions": transactions,
        #         "querytoken": token,
        #         "queryslpaddress": slpaddress,
        #         "slpaddresses": slpaddresses,
        #         "tokens": tokens
        #     })
        # else:
        return render(request, 'base/login.html', query)