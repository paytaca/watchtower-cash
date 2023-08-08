from django.shortcuts import render

from rest_framework import viewsets

from purelypeer.serializers import VaultSerializer
from purelypeer.models import Vault
from paytacapos.pagination import CustomLimitOffsetPagination


class VaultViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Vault.objects.all()
    serializer_class = VaultSerializer
    pagination_class = CustomLimitOffsetPagination
