from rest_framework import (
    decorators,
    status,
    viewsets,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from main.utils.subscription import new_subscription
from main.utils.queries.bchd import BCHDQuery
from main import serializers


class WalletAddressSearchViewSet(viewsets.GenericViewSet):
    serializer_class = serializers.WalletAddressSearchSerializer
    permission_classes = [AllowAny,]

    # `create()` is rest_framework.GenericViewSet's function name for POST
    def create(self, request, *args, **kwargs):
        """
            Subscribe list of address sets only if atleast one of the addresses sets has an existing transaction
        """
        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        bchd = BCHDQuery()
        data = serializer.data
        has_transaction = False
        for address_set in data["address_sets"]:
            txs = bchd.get_address_transactions(address_set["addresses"]["change"], limit=1)
            has_transaction = has_transaction or len(txs.unconfirmed_transactions) or len(txs.confirmed_transactions)
            if has_transaction:
                break

        response = { "success": True }
        if has_transaction:
            for address_set in data["address_sets"]:
                subscription_response = new_subscription(
                    addresses=address_set["addresses"],
                    project_id=data.get("project_id", None),
                    wallet_hash=data["wallet_hash"],
                    address_index=address_set["address_index"],
                )
                if not subscription_response["success"]:
                    response = subscription_response
                    response["address_set"] = address_set
                    break

        return Response(response, status=status.HTTP_200_OK)
