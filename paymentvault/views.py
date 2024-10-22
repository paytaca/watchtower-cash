from rest_framework.response import Response
from rest_framework import viewsets, mixins

from django_filters import rest_framework as filters
from drf_yasg.utils import swagger_auto_schema

from .models import *
from .serializers import *
from .filters import *
from .utils import create_vault


def filter_empty_vaults(vaults):
    loaded_vaults = filter(lambda v: v['balance'] > 0, vaults)
    loaded_vaults = list(loaded_vaults)
    return loaded_vaults


class PaymentVaultViewSet(
    viewsets.GenericViewSet,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin
):
    queryset = PaymentVault.objects.filter(
        merchant__active=True,
        merchant__verified=True
    )
    serializer_class = PaymentVaultSerializer
    filter_backends = (filters.DjangoFilterBackend, )
    filterset_class = PaymentVaultFilterSet

    @swagger_auto_schema(request_body=CreatePaymentVaultSerializer, responses={ 201: serializer_class })
    def create(self, request, *args, **kwargs):
        serializer = CreatePaymentVaultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vault = create_vault(**serializer.validated_data)
        serializer = self.serializer_class(vault)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(filter(serializer.data))

        serializer = self.get_serializer(queryset, many=True)
        return Response(filter(serializer.data))