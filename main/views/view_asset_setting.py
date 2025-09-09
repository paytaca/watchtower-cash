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

from main.serializers import AssetSettingSerializer


class AssetOrderingView(APIView):
	serializer_class = AssetSettingSerializer
	def post(self, request):

		data = request.data
		wallet_hash = request.headers.get('wallet_hash')

		Model = self.serializer_class.Meta.model
		qs = Model.objects.filter(wallet_hash=wallet_hash)

		if qs.exists():
			new_ordering = { "custom_list": data['custom_list']}

			serializer = AssetSettingSerializer(qs.first(), data=new_ordering, partial=True)
			serializer.is_valid(raise_exception=True)
			serializer.save()
		else:
			#stage info
			info = {
				'wallet_hash': wallet_hash,
				'custom_list': data['custom_list']				
			}

			serializer = AssetSettingSerializer(data=info)
			serializer.is_valid(raise_exception=True)
			serializer.save()		
		
		return Response(serializer.data, status=200)

	def get(self, request):
		wallet_hash = request.headers.get('wallet_hash')
		# txid = request.query_params.get('txid')

		Model = self.serializer_class.Meta.model

		qs = Model.objects.filter(wallet_hash=wallet_hash)

		response = {}
		if qs.exists():
			response = AssetSettingSerializer(qs.first()).data
		else:
			return Response({'error': 'Empty Asset Setting'}, status=status.HTTP_404_NOT_FOUND)

		return Response(response["custom_list"], status=200)


class AssetFavoritesView(APIView):
	serializer_class = AssetSettingSerializer

	def post(self, request):
		data = request.data
		wallet_hash = request.headers.get('wallet_hash')

		Model = self.serializer_class.Meta.model
		qs = Model.objects.filter(wallet_hash=wallet_hash)

		if qs.exists():
			favorites = { "favorites": data['favorites']}

			serializer = AssetSettingSerializer(qs.first(), data=favorites, partial=True)
			serializer.is_valid(raise_exception=True)
			serializer.save()
		else:
			#stage info
			info = {
				'wallet_hash': wallet_hash,
				'favorites': data['favorites']				
			}

			serializer = AssetSettingSerializer(data=info)
			serializer.is_valid(raise_exception=True)
			serializer.save()		
		
		return Response(serializer.data, status=200)		

	def get(self, request):
		wallet_hash = request.headers.get('wallet_hash')
		# txid = request.query_params.get('txid')

		Model = self.serializer_class.Meta.model

		qs = Model.objects.filter(wallet_hash=wallet_hash)

		response = {}
		if qs.exists():
			response = AssetSettingSerializer(qs.first()).data
		else:
			return Response({'error': 'Empty Asset Setting'}, status=status.HTTP_404_NOT_FOUND)

		return Response(response["favorites"], status=200)
