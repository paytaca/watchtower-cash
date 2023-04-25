from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import Http404

from ..models.currency import FiatCurrency, CryptoCurrency
from ..serializers.currency import FiatSerializer, CryptoSerializer

class FiatCurrencyList(APIView):
    def get(self, request):
        queryset = FiatCurrency.objects.all()
        serializer = FiatSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

class FiatCurrencyDetail(APIView):
    def get_object(self, pk):
        try:
            return FiatCurrency.objects.get(pk=pk)
        except FiatCurrency.DoesNotExist:
            raise Http404

    def get(self, request, pk):
        fiat = self.get_object(pk)
        serializer = FiatSerializer(fiat)
        return Response(serializer.data, status=status.HTTP_200_OK)

class CryptoCurrencyList(APIView):
    def get(self, request):
        queryset = CryptoCurrency.objects.all()
        serializer = CryptoSerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

class CryptoCurrencyDetail(APIView):
    def get_object(self, pk):
        try:
            return CryptoCurrency.objects.get(pk=pk)
        except CryptoCurrency.DoesNotExist:
            raise Http404

    def get(self, request, pk):
        crypto = self.get_object(pk)
        serializer = CryptoSerializer(crypto)
        return Response(serializer.data, status=status.HTTP_200_OK)