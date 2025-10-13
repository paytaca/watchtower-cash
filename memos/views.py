from django.shortcuts import render
from django.contrib.auth.models import User
from rest_framework.views import APIView, View
from rest_framework.response import Response
from rest_framework import generics, status
from django.db.models import Q
from django.conf import settings 

from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication


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
	authentication_classes = [JWTAuthentication]
	serializer_class = MemoSerializer

	def get_permissions(self):
		if self.request.method == 'GET':
			return [AllowAny()]
		return [IsAuthenticated()]

	def post(self, request):
		data = request.data
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

		Model = self.serializer_class.Meta.model

		qs = Model.objects.filter(wallet_hash=wallet_hash, txid=txid)

		response = {}
		if qs.exists():
			response = MemoSerializer(qs.first()).data
		else:
			return Response({'error': 'Memo not found'}, status=200)

		return Response(response, status=200)

	def patch(self, request):
		data = request.data
		wallet_hash = request.headers.get('wallet_hash')
		txid = data['txid']

		Model = self.serializer_class.Meta.model

		qs = Model.objects.filter(wallet_hash=wallet_hash, txid=txid)

		new_note = { "note": data['note']}
		if qs.exists():
			serializer = MemoSerializer(qs.first(), data=new_note, partial=True)
			serializer.is_valid(raise_exception=True)
			serializer.save()
		else:
			return Response({'error': 'Memo not found'}, status=status.HTTP_404_NOT_FOUND)


		return Response(serializer.data, status=200)

	def delete(self, request):
		wallet_hash = request.headers.get('wallet_hash')
		txid = request.query_params.get('txid')

		Model = self.serializer_class.Meta.model

		qs = Model.objects.filter(wallet_hash=wallet_hash, txid=txid)

		response = {}
		if qs.exists():
			memo = qs.first()

			response = MemoSerializer(memo).data
			memo.delete()

		else:
			return Response({'error': 'Memo not found'}, status=status.HTTP_404_NOT_FOUND)

		return Response({'status': 'successfully deleted', 'data': response}, status=200)

class RegisterView(APIView):
	def post(self, request):
		wallet_hash = request.headers.get('x_authmemo_wallethash')
		memo_user_hash = request.headers.get('x_authmemo_pass')

		if User.objects.filter(username=wallet_hash).exists():
			return Response({'error': 'Username already exists'}, status=400)

		user = User.objects.create_user(
			username=wallet_hash,
			password=memo_user_hash
		)

		return Response({'message': 'User created'}, status=200)