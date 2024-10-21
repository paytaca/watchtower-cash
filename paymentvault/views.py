from rest_framework.response import Response
from rest_framework import viewsets, mixins

from django_filters import rest_framework as filters
from drf_yasg.utils import swagger_auto_schema

from .models import *
from .serializers import *
from .filters import *
from .utils import create_vault


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