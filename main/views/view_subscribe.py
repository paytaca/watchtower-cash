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
        response_status = status.HTTP_409_CONFLICT
        if address:
            address = address.lower()
            if address.startswith('bch') or address.startswith('slp'):
                web_url = request.GET.get('web_url')
                telegram = request.GET.get('telegram_user_details')
                slack = request.GET.get('slack_user_details')
                
                recipient = Recipient()
                recipient.web_url = web_url
                recipient.telegram = telegram
                recipient.slack = slack
                recipient.save()
                    
                if address.startswith('simpleledger'):
                    slp, _ = SlpAddress.objects.get_or_create(address=address)
                    bch = None
                elif address.startswith('bitcoincash'):
                    bch, _ = BchAddress.objects.get_or_create(address=address)
                    slp = None


                subscription = Subscription()
                subscription.recipient = recipient
                subscription.slp = slp
                subscription.bch = bch
                subscription.save()
                response_status = status.HTTP_200_OK
        return Response(status=response_status)