from django.shortcuts import render
from rest_framework.views import APIView, View
from rest_framework.response import Response
from rest_framework import generics, status
from django.db.models import Q
from django.conf import settings 

import json
import requests
import logging
logger = logging.getLogger(__name__)

# Create your views here.
from django.core import serializers

from .serializers import (
    MemoSerializer
)

class MemoView(APIView):

    def post(self, request):
    	data = request.data
    	logger.info('Memos Post View: ')
    	logger.info(data)

    	wallet_hash = request.headers.get('wallet_hash')
    	#stage info
    	info = {
    		'wallet_hash': wallet_hash,
    		'txid': data['txid'],
    		'note': data['note']
    	}

    	serializer = MemoSerializer(data=info)
    	serializer.is_valid(raise_exception=True)
    	serializer.save()

    	return Response(serializer.data, status=200)