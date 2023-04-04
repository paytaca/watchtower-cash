from rest_framework import generics
from ..serializers.ad import AdSerializer
from ..models.ad import Ad

class AdListCreate(generics.ListCreateAPIView):
  queryset = Ad.objects.all()
  serializer_class = AdSerializer

class AdDetail(generics.RetrieveUpdateDestroyAPIView):
  queryset = Ad.objects.all()
  serializer_class = AdSerializer