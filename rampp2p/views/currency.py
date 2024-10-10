from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from django.http import Http404
from rampp2p.models import FiatCurrency, CryptoCurrency
from rampp2p.serializers import FiatCurrencySerializer, CryptoCurrencySerializer
from django.db.models import Count

class FiatCurrencyList(APIView):
    swagger_schema = None
    def get(self, _):
        queryset = FiatCurrency.objects.annotate(paymenttypes_count=Count('payment_types')).filter(paymenttypes_count__gte=1)
        serializer = FiatCurrencySerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

class FiatCurrencyDetail(APIView):
    swagger_schema = None
    def get_object(self, pk):
        try:
            return FiatCurrency.objects.get(pk=pk)
        except FiatCurrency.DoesNotExist:
            raise Http404

    def get(self, request, pk):
        fiat = self.get_object(pk)
        serializer = FiatCurrencySerializer(fiat)
        return Response(serializer.data, status=status.HTTP_200_OK)

class CryptoCurrencyList(APIView):
    swagger_schema = None
    def get(self, request):
        queryset = CryptoCurrency.objects.all()
        serializer = CryptoCurrencySerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

class CryptoCurrencyDetail(APIView):
    swagger_schema = None
    def get_object(self, pk):
        try:
            return CryptoCurrency.objects.get(pk=pk)
        except CryptoCurrency.DoesNotExist:
            raise Http404

    def get(self, request, pk):
        crypto = self.get_object(pk)
        serializer = CryptoCurrencySerializer(crypto)
        return Response(serializer.data, status=status.HTTP_200_OK)