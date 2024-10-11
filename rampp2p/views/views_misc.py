
from rest_framework import status, viewsets
from rest_framework.response import Response

from django.http import Http404
from django.db.models import Count

from rampp2p.models import FiatCurrency, CryptoCurrency
from rampp2p.serializers import FiatCurrencySerializer, CryptoCurrencySerializer

class FiatCurrencyViewSet(viewsets.GenericViewSet):
    serializer_class = FiatCurrencySerializer
    queryset = FiatCurrency.objects.all()

    def list(self, request):
        queryset = self.get_queryset().annotate(paymenttypes_count=Count('payment_types')).filter(paymenttypes_count__gte=1)
        serializer = FiatCurrencySerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

    def retrieve(self, request, pk):
        try:
            fiat = self.get_queryset().get(pk=pk)
            serializer = FiatCurrencySerializer(fiat)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except FiatCurrency.DoesNotExist as err:
            raise Http404
        

class CryptoCurrencyViewSet(viewsets.GenericViewSet):
    serializer_class = CryptoCurrencySerializer
    queryset = FiatCurrency.objects.all()

    def list(self, request):
        queryset = self.get_queryset()
        serializer = CryptoCurrencySerializer(queryset, many=True)
        return Response(serializer.data, status.HTTP_200_OK)

    def retrieve(self, request, pk):
        try:
            crypto = self.get_queryset().get(pk=pk)
            serializer = CryptoCurrencySerializer(crypto)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except CryptoCurrency.DoesNotExist as err:
            raise Http404