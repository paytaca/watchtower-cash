from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class CauldronFeeView(APIView):
    """
    Cauldron DEX fee config for clients charging the Paytaca platform fee
    on token <-> BCH swaps (paytaca-cli, opencode-plugin, paytaca-app).

    A null address means the feature is disabled and clients should
    degrade silently (no fee charged).
    """

    permission_classes = [AllowAny,]

    def get(self, request, format=None):
        return Response(
            {
                "address": settings.CAULDRON_FEE_ADDRESS or None,
                "fee_rate_bps": settings.CAULDRON_FEE,
                "max_usd": str(settings.CAULDRON_FEE_MAX_USD),
            }
        )
