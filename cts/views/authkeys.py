

import requests
import threading
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q, F, CharField, Value
from main.models import (Transaction)

from smartbch.pagination import CustomLimitOffsetPagination

from cts.serializers import AuthKeySerializer

class AuthKeys(APIView):
    
    serializer_class = AuthKeySerializer
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
        responses={status.HTTP_200_OK: AuthKeySerializer},
        manual_parameters=[
            openapi.Parameter('authkey_owner_address', openapi.IN_PATH, description="The current owner of the AuthKey.", type=openapi.TYPE_STRING),
            # openapi.Parameter('exclude_unused_keys', openapi.IN_QUERY, description="Return only AuthKeys with has atleast 1 locked tokens.", type=openapi.TYPE_BOOLEAN),
            openapi.Parameter('offset', openapi.IN_QUERY, description="Pagination's offset.", type=openapi.TYPE_STRING),
            openapi.Parameter('limit', openapi.IN_QUERY, description="Pagination's page limit.Maximum rows per page.", type=openapi.TYPE_INTEGER),
        ]
    )
    def get(self, request, *args, **kwargs):
        queryset = Transaction.objects.filter(spent=False)
        owner_address  = kwargs.get('authkey_owner_address', None)
        if owner_address:
          queryset = queryset.filter(Q(address__address=owner_address) | Q(address__token_address=owner_address))

        authkeys = queryset.filter(
            (Q(amount__isnull=True) | Q(amount=0) ) & 
            Q(cashtoken_nft__category__isnull=False) & 
            Q(cashtoken_nft__commitment='00')
          )
        authkeys = authkeys.annotate(authKeyOwner=Value(owner_address, output_field=CharField()))
        token_authguard_addresses = []
        urls = []
        for authkey in authkeys:
          if authkey.cashtoken_nft.category:
                urls.append(f'http://localhost:3001/cts/js/authguard-token-deposit-address/{authkey.cashtoken_nft.category}')
        
        threads = []
        for url in urls:
            thread = threading.Thread(
                target = lambda u = url: token_authguard_addresses.append(requests.get(u).json())
            )
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

        if self.request.query_params.get('exclude_unused_keys') == 'true':
          # TODO
          # exclude keys that has no unlockable tokens
          # 
          pass
                  
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(authkeys, request)
        if page is not None:
            serializer = self.serializer_class(page, many=True, context={'token_id_authguard_pairs': token_authguard_addresses})
            return paginator.get_paginated_response(serializer.data)

        serializer = self.serializer_class(authkeys, many=True)
        return Response(serializer.data)
    
