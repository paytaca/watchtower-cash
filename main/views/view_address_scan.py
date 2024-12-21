from rest_framework import (
    decorators,
    status,
    viewsets,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from drf_yasg.utils import swagger_auto_schema

from main.utils.subscription import new_subscription
from main.utils.queries.node import Node
from main import serializers


NODE = Node()

class WalletAddressScanViewSet(viewsets.GenericViewSet):
    serializer_class = serializers.WalletAddressScanSerializer
    permission_classes = [AllowAny,]

    @swagger_auto_schema(responses={200: serializers.WalletAddressScanResponseSerializer(many=True)})
    # `create()` is rest_framework.GenericViewSet's function name for POST
    def create(self, request, *args, **kwargs):
        """
            - sorts address sets by address_index
            - attempts to subscribe address_sets from least address_index until the greatest address_index with an address set that has an existing transaction
        """
        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        wallet_hash = serializer.validated_data["wallet_hash"]
        project_id = serializer.validated_data.get("project_id", None)
        sorted_address_sets = serializer.sorted_address_sets()
        sorted_address_sets.reverse() # sorted by address index in descending order

        address_sets_to_subscribe = []
        for i in range(len(sorted_address_sets)):
            address_set = sorted_address_sets[i]

            txs = NODE.BCH.get_address_transactions(address_set["addresses"]["receiving"], limit=1)
            has_transaction = len(txs)

            if not has_transaction:
                txs = NODE.BCH.get_address_transactions(address_set["addresses"]["change"], limit=1)
                has_transaction = len(txs)

            if has_transaction:
                address_sets_to_subscribe = sorted_address_sets[i:]
                break

        # sorted by address index in ascending order after this line
        address_sets_to_subscribe.reverse()

        responses = []
        for address_set in address_sets_to_subscribe:
            response = {
                "success": False,
                "address_set": address_set
            }
            responses.append(response)

        if has_transaction:
            has_error = False
            for response in responses:
                address_set = response["address_set"]

                # if has_error implies that previous address_sets in the loop encountered error, then;
                # succeeding addresss_sets will just skip 
                if not has_error:
                    subscription_response = new_subscription(
                        addresses=address_set["addresses"],
                        project_id=project_id,
                        wallet_hash=wallet_hash,
                        address_index=address_set["address_index"],
                    )
                    response.update(subscription_response)

                if not response["success"]:
                    has_error = True

        return Response(responses, status=status.HTTP_200_OK)
