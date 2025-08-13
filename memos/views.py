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
	serializer_class = MemoSerializer

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


	def get(self, request):
		wallet_hash = request.headers.get('wallet_hash')
		txid = request.query_params.get('txid')

		logger.info('Memos Get View: ')
		logger.info(txid)

		Model = self.serializer_class.Meta.model

		qs = Model.objects.filter(wallet_hash=wallet_hash, txid=txid)

		response = {}
		if qs.exists():
			response = MemoSerializer(qs.first()).data
		else:
			return Response({'error': 'Memo not found'}, status=status.HTTP_404_NOT_FOUND)

		logger.info(response)

		return Response(response, status=200)

	def patch(self, request):
		data = request.data
		wallet_hash = request.headers.get('wallet_hash')
		txid = data['txid']
		logger.info('wallet_hash: ' + wallet_hash)
		logger.info(self.kwargs.get('pk'))

		Model = self.serializer_class.Meta.model

		qs = Model.objects.filter(wallet_hash=wallet_hash, txid=txid)

		new_note = { "note": data['note']}
		if qs.exists():
			serializer = MemoSerializer(qs.first(), data=new_note, partial=True)
			serializer.is_valid(raise_exception=True)
			serializer.save()
			logger.info(serializer.data)
		else:
			return Response({'error': 'Memo not found'}, status=status.HTTP_404_NOT_FOUND)


		return Response(serializer.data, status=200)