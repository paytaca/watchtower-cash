from rest_framework.views import APIView

# FiatListView
class FiatListView(APIView):
  """
  List fiat currencies.
  """

# CryptoListView
class CryptoListView(APIView):
  """
  List crypto currencies.
  """

# FiatDetailView
class FiatDetailView(APIView):
  """
  CRUD a FiatCurrency instance.
  """

# CryptoDetailView
class CryptoDetailView(APIView):
  """
  CRUD a CryptoCurrency instance.
  """