from rest_framework.viewsets import ViewSet
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth import authenticate
from main.models import (
    Subscriber,
    Token as MyToken,
    Subscription,
    SendTo
)
from django.contrib.auth.models import User 
import json
from operator import or_
from django.db.models import Q

class SetupToken(ViewSet):
    
    def get(self, request):
        query = {}
        if request.user.is_authenticated:
            subscriber = Subscriber.objects.get(user=request.user)
            subscriptions = subscriber.subscription.all()
            data = list(subscriptions.values('id','token__name','token__tokenid', 'address__address'))
            return render(request, 'base/setuptoken.html', {"subscriptions": data})
        else:
            return render(request, 'base/login.html', query)

    def post(self, request):
        action = request.POST['action']
        status = 'failed'
        rowid =  request.POST['id']
        name = request.POST.get('name', None)
        sendto = request.POST.get('sendto', None)
        tokenid = request.POST.get('tokenid', None)
        if action == 'delete':
            qs = Subscription.objects.filter(id=rowid)
            if qs.exists():
                subscription = qs.first()
                subscription.delete()
                status = 'success'
        if action == 'add-edit':
            sendto_obj, created = SendTo.objects.get_or_create(address=sendto)
            token_obj, created = MyToken.objects.get_or_create(tokenid=tokenid)
            token_obj.name = name
            token_obj.save()
            if int(rowid) == 0:
                subscriber = Subscriber.objects.get(user=request.user)
                obj = Subscription()
                obj.address = sendto_obj
                obj.token = token_obj
                obj.save()
                subscriber.subscription.add(obj)
                status = 'success'
            else:
                qs = Subscription.objects.filter(id=rowid)
                if qs.exists():
                    qs.update(
                        address=sendto_obj,
                        token=token_obj 
                    )
                status = 'success'
        return JsonResponse({"status": status})


# Token Model ViewSet

from main.models import Token
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from main.serializers import TokenSerializer

class TokenViewSet(viewsets.ModelViewSet):
    """
    A viewset that provides the standard actions
    """
    queryset = Token.objects.all()
    serializer_class = TokenSerializer

