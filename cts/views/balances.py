

import requests
import threading
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q, Sum, Count, F, Value, CharField
from django.db.models.functions import Coalesce

from main.models import (Transaction)

from smartbch.pagination import CustomLimitOffsetPagination

from cts.serializers import FungibleTokenBalanceSerializer

class FungibleTokenBalances(APIView):
    
    serializer_class = FungibleTokenBalanceSerializer
    pagination_class = CustomLimitOffsetPagination
    @swagger_auto_schema(
        operation_description="Fetche of the provided address",
        responses={status.HTTP_200_OK: FungibleTokenBalanceSerializer},
        manual_parameters=[
            openapi.Parameter('address', openapi.IN_PATH, description="Returns aggregated fungible balance of address", type=openapi.TYPE_STRING),
            openapi.Parameter('offset', openapi.IN_QUERY, description="Pagination's offset.", type=openapi.TYPE_STRING),
            openapi.Parameter('limit', openapi.IN_QUERY, description="Pagination's page limit.Maximum rows per page", type=openapi.TYPE_INTEGER),
        ]
    )
    def get(self, request, *args, **kwargs):
        address  = kwargs.get('address', None)
        if address:
          queryset = Transaction.objects.filter(spent=False)
          queryset = queryset.filter(
              Q(amount__gt=0) & 
              Q(cashtoken_ft__category__isnull=False) &
              (Q(address__address=address) | Q(address__token_address=address))
            ) \
            .values('cashtoken_ft__category') \
            .annotate(owner=Value(address, output_field=CharField()), balance=Coalesce(Sum('amount'),0)) \
            .order_by('cashtoken_ft__category').order_by('-balance') \
            .annotate(utxoCount=Count('cashtoken_ft__category'))
        
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data)
    
