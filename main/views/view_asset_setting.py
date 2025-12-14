from django.shortcuts import render
from django.contrib.auth.models import User
from rest_framework.views import APIView, View
from rest_framework.response import Response
from rest_framework import generics, status
from django.db.models import Q
from django.conf import settings 
from django.core.cache import cache

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
	authentication_classes = [JWTAuthentication]
	serializer_class = AssetSettingSerializer

	def get_permissions(self):
		if self.request.method == 'GET':
			return [AllowAny()]
		return [IsAuthenticated()]

	def post(self, request):
		data = request.data
		wallet_hash = request.headers.get('wallet_hash')

		Model = self.serializer_class.Meta.model
		
		try:
			asset_setting = Model.objects.get(wallet_hash=wallet_hash)
			new_ordering = {"custom_list": data['custom_list']}
			serializer = AssetSettingSerializer(asset_setting, data=new_ordering, partial=True)
		except Model.DoesNotExist:
			info = {
				'wallet_hash': wallet_hash,
				'custom_list': data['custom_list']
			}
			serializer = AssetSettingSerializer(data=info)
		
		serializer.is_valid(raise_exception=True)
		serializer.save()
		
		return Response(serializer.data["custom_list"], status=200)

	def get(self, request):
		wallet_hash = request.headers.get('wallet_hash')

		Model = self.serializer_class.Meta.model

		try:
			asset_setting = Model.objects.get(wallet_hash=wallet_hash)
			response = AssetSettingSerializer(asset_setting).data
			return Response(response["custom_list"], status=200)
		except Model.DoesNotExist:
			return Response({'error': 'Empty Asset Setting'}, status=status.HTTP_404_NOT_FOUND)


class AssetFavoritesView(APIView):
	authentication_classes = [JWTAuthentication]
	serializer_class = AssetSettingSerializer

	def get_permissions(self):
		if self.request.method == 'GET':
			return [AllowAny()]
		return [IsAuthenticated()]

	def post(self, request):
		data = request.data
		wallet_hash = request.headers.get('wallet_hash')

		Model = self.serializer_class.Meta.model
		
		# Validate and normalize favorites data
		favorites_data = data.get('favorites', [])
		
		# Ensure it's a list
		if not isinstance(favorites_data, list):
			return Response(
				{'error': 'favorites must be a list'}, 
				status=status.HTTP_400_BAD_REQUEST
			)
		
		# Normalize the structure: ensure each item has {"id": str, "favorite": int}
		normalized_favorites = []
		for item in favorites_data:
			if isinstance(item, dict):
				item_id = item.get('id')
				favorite_value = item.get('favorite', 0)
				
				# Normalize favorite to int (0 or 1)
				if isinstance(favorite_value, str):
					try:
						favorite_value = int(favorite_value)
					except (ValueError, TypeError):
						favorite_value = 0
				elif not isinstance(favorite_value, (int, float)):
					favorite_value = 0
				else:
					favorite_value = 1 if favorite_value == 1 else 0
				
				# Only include items with valid id
				if item_id:
					normalized_favorites.append({
						'id': str(item_id).strip(),
						'favorite': int(favorite_value)
					})
		
		try:
			asset_setting = Model.objects.get(wallet_hash=wallet_hash)
			favorites = {"favorites": normalized_favorites}
			serializer = AssetSettingSerializer(asset_setting, data=favorites, partial=True)
		except Model.DoesNotExist:
			info = {
				'wallet_hash': wallet_hash,
				'favorites': normalized_favorites
			}
			serializer = AssetSettingSerializer(data=info)
		
		serializer.is_valid(raise_exception=True)
		serializer.save()
		
		# Invalidate cache after update to ensure fresh data on next request
		if wallet_hash:
			cache.delete(f'asset_favorites:{wallet_hash}')
		
		return Response(serializer.data["favorites"], status=200)		

	def get(self, request):
		wallet_hash = request.headers.get('wallet_hash')

		Model = self.serializer_class.Meta.model

		try:
			asset_setting = Model.objects.get(wallet_hash=wallet_hash)
			favorites = asset_setting.favorites
			
			# Ensure favorites is a list (should be after migration)
			if not isinstance(favorites, list):
				favorites = []
			
			return Response(favorites, status=200)
		except Model.DoesNotExist:
			return Response({'error': 'Empty Asset Setting'}, status=status.HTTP_404_NOT_FOUND)


class AssetUnlistedView(APIView):
	authentication_classes = [JWTAuthentication]
	serializer_class = AssetSettingSerializer

	def get_permissions(self):
		if self.request.method == 'GET':
			return [AllowAny()]
		return [IsAuthenticated()]

	def post(self, request):
		data = request.data
		wallet_hash = request.headers.get('wallet_hash')

		Model = self.serializer_class.Meta.model
		
		try:
			asset_setting = Model.objects.get(wallet_hash=wallet_hash)
			unlisted_list = {"unlisted_list": data['unlisted_list']}
			serializer = AssetSettingSerializer(asset_setting, data=unlisted_list, partial=True)
		except Model.DoesNotExist:
			info = {
				'wallet_hash': wallet_hash,
				'unlisted_list': data['unlisted_list']
			}
			serializer = AssetSettingSerializer(data=info)
		
		serializer.is_valid(raise_exception=True)
		serializer.save()
		
		return Response(serializer.data["unlisted_list"], status=200)

	def get(self, request):
		wallet_hash = request.headers.get('wallet_hash')

		Model = self.serializer_class.Meta.model

		try:
			asset_setting = Model.objects.get(wallet_hash=wallet_hash)
			response = AssetSettingSerializer(asset_setting).data
			return Response(response["unlisted_list"], status=200)
		except Model.DoesNotExist:
			return Response({'error': 'Empty Asset Setting'}, status=status.HTTP_404_NOT_FOUND)


class RegisterView(APIView):
	def post(self, request):
		wallet_hash = request.headers.get('x_auth_asset_wallethash')
		password = request.headers.get('x_auth_asset_pass')

		if User.objects.filter(username=wallet_hash).exists():
			return Response({'error': 'Username already exists'}, status=400)

		user = User.objects.create_user(
			username=wallet_hash,
			password=password
		)

		return Response({'message': 'User created'}, status=200)