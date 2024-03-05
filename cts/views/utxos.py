

import requests
import threading
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
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
    @swagger_auto_schema(
        operation_description="Fetches the utxos of the provided address",
        responses={status.HTTP_200_OK: UtxoSerializer},
        manual_parameters=[
            openapi.Parameter(name='is_token', type=openapi.TYPE_BOOLEAN, in_=openapi.IN_QUERY, required=False, description="If true, api will only return token utxos."),
            openapi.Parameter('token_type', openapi.IN_QUERY, description="Filters based on type of token. Valid values are 'ft'|'nft'|'hybrid'", type=openapi.TYPE_STRING),
            openapi.Parameter('capability', openapi.IN_QUERY, description="Filters based on NFT capability. Valid values are 'none'|'minting'|'mutable'", type=openapi.TYPE_STRING),
            openapi.Parameter('commitment', openapi.IN_QUERY, description="Filters based on NFT commitment.", type=openapi.TYPE_STRING),
            openapi.Parameter('commitment_ne', openapi.IN_QUERY, description="Only return NFTs with commitment not equal to this value.", type=openapi.TYPE_STRING),
            openapi.Parameter('category', openapi.IN_QUERY, description="Filter by token category", type=openapi.TYPE_STRING),
            openapi.Parameter('offset', openapi.IN_QUERY, description="Pagination's offset.", type=openapi.TYPE_STRING),
            openapi.Parameter('limit', openapi.IN_QUERY, description="Pagination's page limit.Maximum rows per page", type=openapi.TYPE_INTEGER),
        ]
    )
    def get(self, request, *args, **kwargs):
        queryset = Transaction.objects.filter(spent=False)
        address  = kwargs.get('address', None)
        if address:
          queryset = queryset.filter(Q(address__address=address) | Q(address__token_address=address))
        
        is_token = self.request.query_params.get('is_token')
        token_type = self.request.query_params.get('token_type')
        category = self.request.query_params.get('category')

        if is_token == 'true':     # return only token utxos
            queryset = queryset.filter(Q(amount__gt=0) | Q(cashtoken_ft__category__isnull=False) | Q(cashtoken_nft__category__isnull=False))
        
        if token_type == 'ft':     # ft (may have capability also)
            queryset = queryset.filter(Q(amount__gt=0) & Q(cashtoken_ft__category__isnull=False))

        if token_type == 'nft':    # nft (may have ft also)
            queryset = queryset.filter(Q(cashtoken_nft__category__isnull=False) & Q(cashtoken_nft__capability__isnull=False))

        if token_type == 'hybrid': # strictly hybrid
            queryset = queryset.filter(Q(amount__gt=0) & Q(cashtoken_ft__category__isnull=False) & Q(cashtoken_nft__category__isnull=False) & Q(cashtoken_nft__capability__isnull=False))

        if token_type == 'nft' or token_type == 'hybrid':
            capability = self.request.query_params.get('capability')
            commitment = self.request.query_params.get('commitment')
            commitment_ne = self.request.query_params.get('commitment_ne')
            if capability:
                queryset = queryset.filter(cashtoken_nft__capability=capability)
            if commitment:
                queryset = queryset.filter(cashtoken_nft__commitment=commitment)
            if commitment_ne:
                queryset = queryset.filter(~Q(cashtoken_nft__commitment=commitment_ne))
        if category:
            queryset = queryset.filter(~Q(cashtoken_nft__category=category))

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data)
    
