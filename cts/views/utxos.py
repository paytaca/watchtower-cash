

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q

from main.models import (Transaction)

from smartbch.pagination import CustomLimitOffsetPagination

from cts.serializers import UtxoSerializer

class AddressUtxos(APIView):
    
    serializer_class = UtxoSerializer
    pagination_class = CustomLimitOffsetPagination
    # list of
    # interface UtxoI {
    #   txid: string;
    #   vout: number;
    #   satoshis: number;
    #   height?: number;
    #   coinbase?: boolean;
    #   token?: TokenI;
    # }
    def get(self, request, *args, **kwargs):
        queryset = Transaction.objects.filter(spent=False)
        address  = kwargs.get('address', None)
        if address:
          queryset = queryset.filter(Q(address__address=address) | Q(address__token_address=address))
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data)

