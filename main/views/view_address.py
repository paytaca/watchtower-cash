from hashlib import sha224
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from main.models import Address
from main.serializers import AddressInfoSerializer
from notifications.models import DeviceWallet

class AddressInfoView(APIView):
    serializer_class = AddressInfoSerializer

    @swagger_auto_schema(
        responses={200: AddressInfoSerializer},
        manual_parameters=[
            openapi.Parameter('wallet_hash', openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter('project_id', openapi.IN_QUERY, type=openapi.TYPE_STRING),
        ],
    )
    def get(self, request, *args, **kwargs):
        bchaddress = kwargs.get('bchaddress', '')

        filter_kwargs = {}
        query_params = request.query_params
        if "wallet_hash" in query_params:
            filter_kwargs["wallet__wallet_hash"] = query_params["wallet_hash"]

        if "project_id" in query_params:
            filter_kwargs["project__id"] = query_params["project_id"]

        address_obj = Address.objects.filter(
            Q(address=bchaddress) | Q(token_address=bchaddress),
            **filter_kwargs,
        ).first()

        if not address_obj:
            return Response()

        wallet = getattr(address_obj, "wallet", None)
        wallet_hash = getattr(wallet, "wallet_hash", "")
        project_id = getattr(address_obj, "project_id", "") or getattr(wallet, "project_id", "")
        has_subscribed_push_notifications = False

        if wallet_hash:
            has_subscribed_push_notifications = DeviceWallet.objects \
                .filter(wallet_hash=wallet_hash) \
                .filter(Q(gcm_device__active=True) | Q(apns_device__active=True)) \
                .exists()

        wallet_digest = None
        if address_obj.wallet and address_obj.wallet.wallet_hash:
            wallet_hash_bytes = bytes.fromhex(address_obj.wallet.wallet_hash)
            wallet_digest = sha224(wallet_hash_bytes).digest().hex()

        serializer = self.serializer_class(dict(
            address=address_obj.address,
            token_address=address_obj.token_address,
            wallet_digest=wallet_digest,
            project_id=project_id,
            address_path=address_obj.address_path,
            wallet_index=address_obj.wallet_index,
            has_subscribed_push_notifications=has_subscribed_push_notifications,
        ))
        return Response(serializer.data)
