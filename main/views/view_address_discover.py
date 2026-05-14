import logging

from rest_framework import (
    status,
    viewsets,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from drf_yasg.utils import swagger_auto_schema

from main.utils.queries.node import Node
from main import serializers

LOGGER = logging.getLogger(__name__)

NODE = Node()


class WalletAddressDiscoverViewSet(viewsets.GenericViewSet):
    serializer_class = serializers.WalletAddressDiscoverSerializer
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        responses={200: serializers.WalletAddressDiscoverResponseSerializer()}
    )
    def create(self, request, *args, **kwargs):
        """
        Checks a batch of address sets for transaction history against the BCH node.

        For each address set (receiving + change), efficiently queries the Electrum/Fulcrum
        server to determine if the address has any transaction history. Uses blockchain.address.get_first_use
        for O(1) checks instead of loading full transaction history — efficient even for
        addresses with thousands of transactions (e.g., exchange hot wallets).

        An address with zero balance but transaction history is still flagged as having
        history — important for recovering wallets used by other software (e.g., Electron
        Cash CashFusion) where coins may have moved through many addresses.

        This endpoint does NOT subscribe addresses — it only reports which addresses
        have history. The client is expected to follow up with a call to
        wallet/address-scan/ to subscribe discovered addresses.

        Request body:
            wallet_hash: str
            project_id: str (optional)
            address_sets: list of { address_index: int, receiving: str, change: str }
        """
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        address_sets = serializer.validated_data["address_sets"]
        wallet_hash = serializer.validated_data.get("wallet_hash", "")

        results = []
        for address_set in address_sets:
            address_index = address_set["address_index"]
            receiving_address = address_set.get("receiving")
            change_address = address_set.get("change")

            receiving_has_history = False
            change_has_history = False

            result = {
                "address_index": address_index
            }

            if receiving_address:
                try:
                    receiving_has_history = NODE.BCH.check_address_history(
                        receiving_address
                    )
                    result["receiving"] = {
                        "address": receiving_address,
                        "has_history": receiving_has_history
                    }

                except Exception:
                    LOGGER.warning(
                        "Failed to check transaction history for receiving address: %s",
                        receiving_address,
                    )

            if change_address:
                try:
                    change_has_history = NODE.BCH.check_address_history(change_address)
                    result["change"] = {
                        "address": change_address,
                        "has_history": change_has_history
                    }
                except Exception:
                    LOGGER.warning(
                        "Failed to check transaction history for change address: %s",
                        change_address,
                    )

            results.append(result)

        return Response({"results": results}, status=status.HTTP_200_OK)
