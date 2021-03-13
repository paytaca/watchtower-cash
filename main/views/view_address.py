from rest_framework.viewsets import ViewSet
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.contrib.auth import authenticate, login, logout
from main.models import (
    Subscriber,
    Token as MyToken,
    Transaction,
    Subscription,
    SendTo,
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

class SetAddressView(APIView):
    """
    Subscribers can set address using api view.
    * Requfires token authentication.
    * Permission should be authenticated.
    """
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    

    def post(self, request, format=None):
        tokenaddress = request.data.get('tokenAddress', None)
        destinationAddress = request.data.get('destinationAddress', None)
        tokenid = request.data.get('tokenid', None)
        tokenname = request.data.get('tokenname', None)
        reason = 'Invalid params.'
        status = 'failed'
        if tokenaddress and destinationAddress and tokenid and tokenname:
            subscriber_qs = Subscriber.objects.filter(user=request.user)
            reason = 'Not yet subscribed.'
            if subscriber_qs.exists():
                subscriber = subscriber_qs.first()
                sendto_obj, created = SendTo.objects.get_or_create(address=destinationAddress)
                if 'bitcoincash' in tokenaddress:
                    address_obj, created = BchAddress.objects.get_or_create(address=tokenaddress)
                    subscription_obj, created = Subscription.objects.get_or_create(bch=address_obj)
                    reason = 'BCH added.'
                else:
                    address_obj, created = SlpAddress.objects.get_or_create(address=tokenaddress)
                    subscription_obj, created = Subscription.objects.get_or_create(slp=address_obj)
                    reason = 'SLP added.'
                if tokenid is not None:
                    token_obj, created =  MyToken.objects.get_or_create(tokenid=tokenid)
                    token_obj.name = tokenname.lower()
                    subscription_obj.token = token_obj
                subscription_obj.save()
                subscription_obj.address.add(sendto_obj)
                subscriber.subscriptions.add(subscription_obj)
                status = 'success'
        return Response({'status': status, 'reason': reason})