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

CHAINS = ("receiving", "change")


class WalletAddressDiscoverViewSet(viewsets.GenericViewSet):
    serializer_class = serializers.WalletAddressDiscoverSerializer
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        responses={200: serializers.WalletAddressDiscoverResponseSerializer()}
    )
    def create(self, request, *args, **kwargs):
        """
        Checks a batch of address sets for transaction history against the BCH node.

        For each address set (receiving and change), efficiently
        queries the Electrum/Fulcrum server to determine if the address has any
        transaction history. Uses blockchain.address.get_first_use for O(1)
        checks instead of loading full transaction history — efficient even for
        addresses with thousands of transactions (e.g., exchange hot wallets).

        The whole batch is checked over a single Fulcrum connection. An address
        with zero balance but transaction history is still flagged as having
        history — important for recovering wallets used by other software (e.g.,
        Electron Cash CashFusion) where coins may have moved through many
        addresses.

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

        addresses = []
        for address_set in address_sets:
            for chain in CHAINS:
                if address_set.get(chain):
                    addresses.append(address_set[chain])

        try:
            history = NODE.BCH.check_addresses_history(addresses)
        except Exception:
            LOGGER.exception("Failed to check transaction history for an address batch")
            return Response(
                {"error": "address_discovery_failed"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        results = []
        for address_set in address_sets:
            result = {"address_index": address_set["address_index"]}

            for chain in CHAINS:
                address = address_set.get(chain)
                if not address:
                    continue
                if address not in history:
                    LOGGER.error(
                        "Missing transaction history result for %s address: %s",
                        chain,
                        address,
                    )
                    return Response(
                        {"error": "address_discovery_incomplete"},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                result[chain] = {
                    "address": address,
                    "has_history": history[address],
                }

            results.append(result)

        return Response({"results": results}, status=status.HTTP_200_OK)
