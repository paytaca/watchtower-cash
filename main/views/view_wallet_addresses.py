from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from main.models import Wallet, Address
# from main.serializers import WalletAddressesSerializer

class WalletAddressesView(APIView):
    # serializer_class = WalletAddressesSerializer

    @swagger_auto_schema(
        operation_description="Returns the addresses of provided wallet hash",
        responses={status.HTTP_200_OK: openapi.Response(
            description="List of wallet addresses",
            examples={
                'application/json': [
                    'bitcoincash:qqscs5frlmjmvdscm741mruau9ctsn2le5khg7gl92', 
                    'bitcoincash:qzzkvnxky1ztgp0xvex7hfu6g92tdwzh9gagyaz2hj'
                ]

            },
            type=openapi.TYPE_ARRAY,
            items=openapi.Items(type=openapi.TYPE_STRING)
        )},
        manual_parameters=[
            openapi.Parameter('change_index', openapi.IN_QUERY, description="Filters based on change index of BIP44 derivation path. Set to 0 for external or deposit addresses, 1 for change addresses.", required=False, type=openapi.TYPE_INTEGER),
            openapi.Parameter('address_index', openapi.IN_QUERY, description="Filters based on address_index of BIP44 derivation path.", required=False, type=openapi.TYPE_INTEGER),
        ]
    )
    def get(self, request, *args, **kwargs):
        wallet_hash = kwargs.get('wallethash', '')
        change_index = self.request.query_params.get('change_index', None)
        address_index = self.request.query_params.get('address_index', '\d+')

        wallet_addresses = Address.objects.filter(wallet__wallet_hash=wallet_hash)
        
        address_path_filter = ''
        
        if change_index != None:
            address_path_filter = address_path_filter + f'{change_index}/{address_index}'

        if address_path_filter:
            wallet_addresses = wallet_addresses.filter(
                address_path__iregex=address_path_filter
            )
        wallet_addresses = wallet_addresses.order_by('address_path').values_list('address', flat=True)

        return Response(list(wallet_addresses))