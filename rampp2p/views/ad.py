from rest_framework import generics
from rest_framework.views import APIView
from django.db.models import Prefetch
from ..serializers.ad import AdSerializer
from ..models.ad import Ad

class AdList(generics.ListAPIView):
  queryset = Ad.objects.all().prefetch_related('owner', 'fiat_currency', 'crypto_currency')
  serializer_class = AdSerializer

class AdCreate(APIView):
  def post(self, request):
    pass

class AdDetail(generics.RetrieveUpdateDestroyAPIView):
  queryset = Ad.objects.all()
  serializer_class = AdSerializer