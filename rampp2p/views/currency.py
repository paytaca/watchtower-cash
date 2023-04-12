from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import Http404
from ..models.currency import FiatCurrency, CryptoCurrency
from ..serializers.currency import FiatSerializer, CryptoSerializer

# TODO Limit write endpoints to admin permissions

class FiatCurrencyList(APIView):
  # permission_classes = [IsAuthenticatedOrReadOnly]

  # list fiat currencies
  def get(self, request):
    queryset = FiatCurrency.objects.all()
    serializer = FiatSerializer(queryset, many=True)
    return Response(serializer.data, status.HTTP_200_OK)

  # create fiat currency
  def post(self, request):
    serializer = FiatSerializer(data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class FiatCurrencyDetail(APIView):
  # permission_classes = [IsAuthenticatedOrReadOnly]

  # get fiat object
  def get_object(self, pk):
    try:
      return FiatCurrency.objects.get(pk=pk)
    except FiatCurrency.DoesNotExist:
      raise Http404

  # get fiat currency
  def get(self, request, pk):
    fiat = self.get_object(pk)
    serializer = FiatSerializer(fiat)
    return Response(serializer.data, status=status.HTTP_200_OK)

  # update fiat currency
  def put(self, request, pk):
    fiat = self.get_object(pk)
    serializer = FiatSerializer(fiat, data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

  # delete fiat currency
  def delete(self, request, pk):
    fiat = self.get_object(pk)
    fiat.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

class CryptoCurrencyList(APIView):
  # permission_classes = [IsAuthenticatedOrReadOnly]

  # list crypto currencies
  def get(self, request):
    queryset = CryptoCurrency.objects.all()
    serializer = CryptoSerializer(queryset, many=True)
    return Response(serializer.data, status.HTTP_200_OK)

  # create crypto currency
  def post(self, request):
    serializer = CryptoSerializer(data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CryptoCurrencyDetail(APIView):
  # permission_classes = [IsAuthenticatedOrReadOnly]

  # get object
  def get_object(self, pk):
    try:
      return CryptoCurrency.objects.get(pk=pk)
    except CryptoCurrency.DoesNotExist:
      raise Http404

  # get crypto currency
  def get(self, request, pk):
    crypto = self.get_object(pk)
    serializer = CryptoSerializer(crypto)
    return Response(serializer.data, status=status.HTTP_200_OK)

  # update crypto currency
  def put(self, request, pk):
    crypto = self.get_object(pk)
    serializer = CryptoSerializer(crypto, data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

  # delete crypto currency
  def delete(self, request, pk):
    crypto = self.get_object(pk)
    crypto.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)