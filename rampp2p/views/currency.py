from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import Http404
from django.contrib.auth.mixins import UserPassesTestMixin

from ..models.currency import FiatCurrency, CryptoCurrency
from ..serializers.currency import FiatSerializer, CryptoSerializer

class FiatCurrencyList(UserPassesTestMixin, APIView):
    # Require admin authentication or read-only access
    def test_func(self):
        user = self.request.user
        return (
          self.request.method in ['GET', 'HEAD'] or 
            (user.is_authenticated and user.is_superuser)
        )

    def get(self, request):
        queryset = FiatCurrency.objects.all()
        serializer = FiatSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

class FiatCurrencyDetail(UserPassesTestMixin, APIView):
    # Require admin authentication or read-only access
    def test_func(self):
        user = self.request.user
        return (
          self.request.method in ['GET', 'HEAD'] or 
            (user.is_authenticated and user.is_superuser)
        )

    def get_object(self, pk):
        try:
            return FiatCurrency.objects.get(pk=pk)
        except FiatCurrency.DoesNotExist:
            raise Http404

    def get(self, request, pk):
        fiat = self.get_object(pk)
        serializer = FiatSerializer(fiat)
        return Response(serializer.data, status=status.HTTP_200_OK)

class CryptoCurrencyList(UserPassesTestMixin, APIView):
     # Require admin authentication or read-only access
    def test_func(self):
        user = self.request.user
        return (
          self.request.method in ['GET', 'HEAD'] or 
            (user.is_authenticated and user.is_superuser)
        )

    def get(self, request):
        queryset = CryptoCurrency.objects.all()
        serializer = CryptoSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

class CryptoCurrencyDetail(APIView):
    # Require admin authentication or read-only access
    def test_func(self):
        user = self.request.user
        return (
          self.request.method in ['GET', 'HEAD'] or 
            (user.is_authenticated and user.is_superuser)
        )

    def get_object(self, pk):
        try:
            return CryptoCurrency.objects.get(pk=pk)
        except CryptoCurrency.DoesNotExist:
            raise Http404

    def get(self, request, pk):
        crypto = self.get_object(pk)
        serializer = CryptoSerializer(crypto)
        return Response(serializer.data, status=status.HTTP_200_OK)