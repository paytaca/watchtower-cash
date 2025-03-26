from django.http import JsonResponse
from rest_framework import viewsets
from main.models import AppControl
from main.serializers import AppControlSerializer

class AppControlViewSet (viewsets.ModelViewSet):
    queryset = AppControl.objects.all()
    serializer_class = AppControlSerializer