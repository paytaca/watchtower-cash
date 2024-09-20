from rest_framework.response import Response
from rest_framework.views import APIView

from main.models import Wallet
from main.serializers import WalletAddressesSerializer

class WalletAddressesView(APIView):
    serializer_class = WalletAddressesSerializer

    def get(self, request, *args, **kwargs):
        wallet_hash = kwargs.get('wallethash', '')
        wallet_addresses = []

        wallet_check = Wallet.objects.filter(wallet_hash=wallet_hash)
        if wallet_check.exists():
            for address in wallet_check.first().addresses.all():
                wallet_addresses.append(address.address)

        return Response(wallet_addresses)