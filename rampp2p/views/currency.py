from rest_framework import generics
from ..models.currency import FiatCurrency, CryptoCurrency
from ..serializers.currency import FiatSerializer, CryptoSerializer

class FiatListCreateView(generics.ListCreateAPIView):
  queryset = FiatCurrency.objects.all()
  serializer_class = FiatSerializer

class FiatDetailView(generics.RetrieveUpdateDestroyAPIView):
  queryset = FiatCurrency.objects.all()
  serializer_class = FiatSerializer

class CryptoListCreateView(generics.ListCreateAPIView):
  queryset = CryptoCurrency.objects.all()
  serializer_class = CryptoSerializer

class CryptoDetailView(generics.RetrieveUpdateDestroyAPIView):
  queryset = CryptoCurrency.objects.all()
  serializer_class = CryptoSerializer