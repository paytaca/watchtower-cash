

from typing import Any
import requests
import threading
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q, F, CharField, Value

from main.models import (Transaction, BlockHeight)

from smartbch.pagination import CustomLimitOffsetPagination

from cts.serializers import UtxoSerializer, AuthchainIdentitySerializer



class AuthchainIdentity(APIView):
    serializer_class = AuthchainIdentitySerializer
    pagination_class = CustomLimitOffsetPagination
    """
    These API identifies the utxos that are 'IdentityOutput'(s) in the context of BCMR.
    In CashToken Studio's case these IdentityOutputs are tokens that 
    are ALSO locked in an AuthGuard contract where the AuthKey(NFT) is currently owned by the 
    'authkey_owner_address' in this view's path parameter.

    The AuthGuard contract owns the actual IdentityOutput tokens. So anyone owns the AuthKey
    of a particular AuthGuard also owns the IdentityOutput tokens locked on the AuthGuard.
    """
    @swagger_auto_schema(
        operation_description="Fetches the identity outputs associated with the (owner's) address",
        responses={status.HTTP_200_OK: AuthchainIdentitySerializer},
        manual_parameters=[
            openapi.Parameter('authkey_owner_address', openapi.IN_PATH, description="The address that currently owns the AuthKey (NFT) that can unlock the AuthGuard that stores the IdentityOutputs", type=openapi.TYPE_STRING),
            openapi.Parameter('authguard', openapi.IN_QUERY, description="The Authguard contract's token address. This filters results by Authguard contract's token address. Returns only the IdentityOutputs locked in this Authguard", type=openapi.TYPE_STRING),
            openapi.Parameter('token_amount__eq', openapi.IN_QUERY, description="Filters identities with token amount equal to the provided value", type=openapi.TYPE_INTEGER),
            openapi.Parameter('token_amount__lte', openapi.IN_QUERY, description="Filters identities with token amount less than or equal to the provided value.", type=openapi.TYPE_INTEGER),
            openapi.Parameter('token_amount__gte', openapi.IN_QUERY, description="Filters identities with token amount greater than or equal to the provided value. This can be used to filter identities holds FT reserve supply.", type=openapi.TYPE_INTEGER),
            openapi.Parameter('token_is_nft', openapi.IN_QUERY, description="Filters identities with nft capability", type=openapi.TYPE_BOOLEAN),
            openapi.Parameter('token_capability', openapi.IN_QUERY, description="Filters identities by nft capability", type=openapi.TYPE_STRING),
            openapi.Parameter('token_commitment', openapi.IN_QUERY, description="Filters identities by nft commitment", type=openapi.TYPE_STRING),
            openapi.Parameter('offset', openapi.IN_QUERY, description="Pagination's offset.", type=openapi.TYPE_STRING),
            openapi.Parameter('limit', openapi.IN_QUERY, description="Pagination's page limit.Maximum rows per page", type=openapi.TYPE_INTEGER),
        ]
    )
    def get(self, request, *args, **kwargs):
        queryset = Transaction.objects.filter(spent=False)
        address  = kwargs.get('authkey_owner_address', None)
        if address:
          queryset = queryset.filter(Q(address__address=address) | Q(address__token_address=address))
        
        queryset = queryset.filter(Q(cashtoken_ft__category__isnull=False) | Q(cashtoken_nft__category__isnull=False))
        authkeys = queryset.filter(cashtoken_nft__commitment='00') # authkey like
        # We need to get the addresses of the AuthGuard contract
        # associated with each of these AuthKeys.
        # We'll save it here 
        token_authguard_addresses = [] # [{ <category or tokenId>: <authguard contract token deposit address> }, ...]
        # authkeycategory = Authguard() = 1 address
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
        
        authguard_addresses_set = set(map(lambda x: x[list(x.keys())[0]], token_authguard_addresses))
        identity_outputs = Transaction.objects.filter(
            Q(spent=False),
            Q(index=0), Q(address__token_address__in=authguard_addresses_set) | Q(address__token_address__in=authguard_addresses_set)
        ) \
         .annotate(authGuard=F('address__token_address')) \
         .annotate(authKeyOwner=Value(address, output_field=CharField()))

        if self.request.query_params.get('authguard'):
            identity_outputs = identity_outputs.filter(address__token_address=self.request.query_params.get('authguard'))

        if self.request.query_params.get('token_amount__eq'):
            identity_outputs = identity_outputs.filter(amount=int(self.request.query_params.get('token_amount__eq')))

        if self.request.query_params.get('token_amount__lte'):
            identity_outputs = identity_outputs.filter(amount__lte=int(self.request.query_params.get('token_amount__lte')))

        if self.request.query_params.get('token_amount__gte'):
            identity_outputs = identity_outputs.filter(amount__gte=int(self.request.query_params.get('token_amount__gte')))

        if self.request.query_params.get('token_is_nft'):
            identity_outputs = identity_outputs.filter(cashtoken_nft__capability__isnull=False)

        if self.request.query_params.get('token_capability'):
            identity_outputs = identity_outputs.filter(cashtoken_nft__capability=self.request.query_params.get('token_capability'))
        
        if self.request.query_params.get('token_commitment'):
            identity_outputs = identity_outputs.filter(cashtoken_nft__commitment=self.request.query_params.get('token_commitment'))
        

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(identity_outputs, request)

        if page is not None:
            serializer = self.serializer_class(page, many=True, context={'token_id_authguard_pairs': token_authguard_addresses})
            return paginator.get_paginated_response(serializer.data)
        
class Authhead(APIView):
    serializer_class = UtxoSerializer
    @swagger_auto_schema(
        operation_description="Returns the current authhead of the authchain.",
        responses={status.HTTP_200_OK: UtxoSerializer},
        manual_parameters=[
            openapi.Parameter('authbase', openapi.IN_QUERY, description="The authbase(txid) of the authchain", type=openapi.TYPE_STRING),
        ]
    )
    def get(self, request, *args, **kwargs):
        authhead = Authhead.get_authhead(request)
        if authhead and not authhead.spent:
            s = UtxoSerializer(authhead, many=False)
            return Response(data={'authhead': s.data, 'address': authhead.address.address})
        else: 
            Response(None)

    @staticmethod
    def get_authhead(request):
        authbase = request.query_params.get('authbase')
        identity_output = None
        identity_output_tx = authbase 
        authhead = None
        max_chain_length = BlockHeight.objects.order_by('number').last().number
        count = 0
        while authhead == None:
            count += 1
            if count == max_chain_length:
                break
            identity_output = Transaction.objects.filter(txid=identity_output_tx, index=0)
            if identity_output:
                identity_output = identity_output.first()
                identity_output_tx = identity_output.spending_txid
                if identity_output.spent == True:
                    continue
                else:
                    authhead = identity_output
                    break
            else:
                break

        return authhead
        
      

class Authenticate(APIView):
    serializer_class = UtxoSerializer
    @swagger_auto_schema(
        operation_description="Authenticates the authhead. Checks that the authhead is the last, unspent, zeroeth descendant output of the authbase.",
        responses={status.HTTP_200_OK: UtxoSerializer},
        manual_parameters=[
            openapi.Parameter('authbase', openapi.IN_QUERY, description="The authbase (txid, is usually also the tokenId)", type=openapi.TYPE_STRING),
            openapi.Parameter('authhead', openapi.IN_QUERY, description="The authhead (txid)", type=openapi.TYPE_STRING),
        ]
    )
    def post(self, request, *args, **kwargs):
        authhead = Authhead.get_authhead(request)
        authhead_param = request.query_params.get('authhead')
        if authhead.txid == authhead_param and not authhead.spent:
            s = UtxoSerializer(authhead, many=False)
            return Response(data={'authhead': s.data, 'address': authhead.address.address, 'success': 'Authhead checked ok'})
        return Response(data={'failed': f'Authhead checked nok'})



