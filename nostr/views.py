from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from .serializers import (
    PubkeyRegisterSerializer,
    PubkeyUnregisterSerializer,
    PubkeyLastOnlineSerializer,
)
from .authentication import BitcoinCashOAuthAuthentication
from .models import NostrPubkey
from main.models import Wallet


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

        np_records = list(NostrPubkey.objects.filter(
            pubkey_hex__in=pubkeys,
        ).values('pubkey_hex', 'wallet_hash', 'last_active'))

        mapping = {}
        for np in np_records:
            mapping.setdefault(np['pubkey_hex'], []).append({
                'wallet_hash': np['wallet_hash'],
                'last_active': np['last_active'],
            })

        all_wallet_hashes = list(set(
            wh['wallet_hash']
            for whs in mapping.values()
            for wh in whs
        ))

        wallets = {
            w.wallet_hash: w.last_balance_check
            for w in Wallet.objects.filter(wallet_hash__in=all_wallet_hashes)
        }

        result = {}
        for pubkey in pubkeys:
            timestamps = []
            for entry in mapping.get(pubkey, []):
                if entry['last_active']:
                    timestamps.append(entry['last_active'])
                if wallets.get(entry['wallet_hash']):
                    timestamps.append(wallets[entry['wallet_hash']])

            max_ts = max(timestamps).isoformat().replace('+00:00', 'Z') if timestamps else None
            result[pubkey] = max_ts

        return Response(result, status=status.HTTP_200_OK)


class PubkeyCheckView(APIView):
    """Check if a Nostr pubkey is registered with watchtower."""
    permission_classes = []

    def get(self, request, pubkey_hex, *args, **kwargs):
        is_registered = NostrPubkey.objects.filter(pubkey_hex=pubkey_hex).exists()
        return Response({
            "pubkey_hex": pubkey_hex,
            "registered": is_registered,
        }, status=status.HTTP_200_OK)
