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

        For each address set (receiving + change), queries the Electrum/Fulcrum server
        to determine if the address has any transaction history. An address with zero
        balance but transaction history is still flagged as having history — important
        for recovering wallets used by other software (e.g. Electron Cash CashFusion)
        where coins may have moved through many addresses.

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
            receiving_address = address_set["receiving"]
            change_address = address_set["change"]

            receiving_has_history = False
            change_has_history = False

            try:
                receiving_txs = NODE.BCH.get_address_transactions(receiving_address)
                receiving_has_history = bool(receiving_txs)
            except Exception:
                LOGGER.warning(
                    "Failed to check transaction history for receiving address: %s",
                    receiving_address,
                )

            try:
                change_txs = NODE.BCH.get_address_transactions(change_address)
                change_has_history = bool(change_txs)
            except Exception:
                LOGGER.warning(
                    "Failed to check transaction history for change address: %s",
                    change_address,
                )

            results.append(
                {
                    "address_index": address_index,
                    "receiving": {
                        "address": receiving_address,
                        "has_history": receiving_has_history,
                    },
                    "change": {
                        "address": change_address,
                        "has_history": change_has_history,
                    },
                }
            )

        return Response({"results": results}, status=status.HTTP_200_OK)
