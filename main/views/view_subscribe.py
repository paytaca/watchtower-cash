from rest_framework.viewsets import ViewSet
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse


from django.views import View
from django.contrib.auth import authenticate, login, logout
from main.models import (
    Subscription,
    Recipient,
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
from rest_framework import status

from rest_framework import authentication, permissions
from rest_framework.decorators import action


class SubscribeViewSet(APIView):
    
    def get(self, request, format=None):
        address = request.GET.get('address', None)
        web_url = request.GET.get('web_url', None)
        response_status = status.HTTP_409_CONFLICT
        if address and web_url:
            if web_url.lower().startswith('http'):
                address = address.lower()
                if address.startswith('bitcoincash:') or address.startswith('simpleledger:'):
                    
                    recipient, _ = Recipient.objects.get_or_create(web_url=web_url)
                        
                    bch = None
                    slp = None

                    if address.startswith('simpleledger'):
                        slp, _ = SlpAddress.objects.get_or_create(address=address)
                    elif address.startswith('bitcoincash'):
                        bch, _ = BchAddress.objects.get_or_create(address=address)
                    

                    subscription, created = Subscription.objects.get_or_create(recipient=recipient,slp=slp,bch=bch)
                    if created:

                        response_status = status.HTTP_200_OK
        return Response(status=response_status)