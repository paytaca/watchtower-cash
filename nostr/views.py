from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from .serializers import (
    PubkeyRegisterSerializer,
    PubkeyUnregisterSerializer,
    PubkeyLastOnlineSerializer,
    PubkeyTouchSerializer,
)
from .authentication import BitcoinCashOAuthAuthentication
from .models import NostrPubkey
from main.utils.cache import get_last_active, set_last_active
from nostr.utils.websocket import send_last_active_update


class PubkeyRegisterView(APIView):
    authentication_classes = [BitcoinCashOAuthAuthentication]
    permission_classes = []
    serializer_class = PubkeyRegisterSerializer

    @swagger_auto_schema(
        request_body=PubkeyRegisterSerializer,
        responses={201: PubkeyRegisterSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "registered"}, status=status.HTTP_201_CREATED)


class PubkeyUnregisterView(APIView):
    authentication_classes = [BitcoinCashOAuthAuthentication]
    permission_classes = []
    serializer_class = PubkeyUnregisterSerializer

    @swagger_auto_schema(
        request_body=PubkeyUnregisterSerializer,
        responses={200: PubkeyUnregisterSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "unregistered"}, status=status.HTTP_200_OK)


class PubkeyLastOnlineView(APIView):
    """Return the latest online timestamp for each requested pubkey.

    This endpoint is intentionally public — last-online status is meant to be
    accessible by any client (e.g., chat UIs that display online indicators).
    The data returned is non-sensitive: it only indicates whether a pubkey has
    been recently active (registered, received a Nostr message, or polled the
    watchtower).
    """
    permission_classes = []
    serializer_class = PubkeyLastOnlineSerializer

    @swagger_auto_schema(
        request_body=PubkeyLastOnlineSerializer,
        responses={200: PubkeyLastOnlineSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        pubkeys = serializer.validated_data['pubkeys']

        result = {}
        uncached_pubkeys = []

        for pubkey in pubkeys:
            cached = get_last_active(pubkey)
            if cached is not None:
                result[pubkey] = cached
            else:
                uncached_pubkeys.append(pubkey)

        if uncached_pubkeys:
            np_records = {
                np['pubkey_hex']: np['last_active']
                for np in NostrPubkey.objects.filter(
                    pubkey_hex__in=uncached_pubkeys,
                ).values('pubkey_hex', 'last_active')
            }

            for pubkey in uncached_pubkeys:
                last_active = np_records.get(pubkey)
                max_ts = last_active.isoformat().replace('+00:00', 'Z') if last_active else None
                result[pubkey] = max_ts

                if max_ts is not None:
                    set_last_active(pubkey, max_ts)

        return Response(result, status=status.HTTP_200_OK)


class PubkeyTouchView(APIView):
    """Touch endpoint — the sender calls this right after sending a message.

    Updates the sender's ``last_active`` and pushes a real-time notification
    to each recipient's WebSocket room so their green dot lights up.
    """
    authentication_classes = [BitcoinCashOAuthAuthentication]
    permission_classes = []
    serializer_class = PubkeyTouchSerializer

    @swagger_auto_schema(
        request_body=PubkeyTouchSerializer,
        responses={200: "ok"},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        sender_pubkey = serializer.validated_data['pubkey']
        recipients = serializer.validated_data['recipients']

        try:
            np_sender = NostrPubkey.objects.only('wallet_hash').get(
                pubkey_hex=sender_pubkey,
            )
        except NostrPubkey.DoesNotExist:
            return Response(
                {"error": "Sender pubkey not registered"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()

        NostrPubkey.objects.filter(pubkey_hex=sender_pubkey).update(last_active=now)
        set_last_active(sender_pubkey, now)

        if recipients:
            room_map = {
                np['pubkey_hex']: np['wallet_hash']
                for np in NostrPubkey.objects.filter(
                    pubkey_hex__in=recipients,
                ).values('pubkey_hex', 'wallet_hash')
            }

            for recipient_pubkey in recipients:
                wallet_hash = room_map.get(recipient_pubkey)
                if wallet_hash:
                    send_last_active_update(wallet_hash, sender_pubkey, now)

        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class PubkeyCheckView(APIView):
    """Check if a Nostr pubkey is registered with watchtower."""
    permission_classes = []

    def get(self, request, pubkey_hex, *args, **kwargs):
        is_registered = NostrPubkey.objects.filter(pubkey_hex=pubkey_hex).exists()
        return Response({
            "pubkey_hex": pubkey_hex,
            "registered": is_registered,
        }, status=status.HTTP_200_OK)
