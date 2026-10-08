from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from authentication.token import WalletAuthentication
from main.models import WalletLookupKey
from main.serializers import (
    WalletLookupKeyCreateSerializer,
    WalletLookupKeyCreatedSerializer,
    WalletLookupKeyBalanceSerializer,
)
from main.throttles import WalletLookupKeyThrottle
from main.utils.wallet_balances import (
    InvalidAssetId,
    get_wallet_balances,
    parse_assets_param,
)
from main.utils.wallet_lookup_key import (
    generate_raw_key,
    hash_key,
    resolve_key,
)

import logging
logger = logging.getLogger(__name__)

LOOKUP_KEY_HEADER = 'HTTP_X_API_KEY'


def get_lookup_key_from_request(request):
    """Read the raw lookup key from the X-Api-Key header."""
    return (
        request.headers.get('x-api-key')
        or request.headers.get('X-Api-Key')
        or request.META.get(LOOKUP_KEY_HEADER)
        or ''
    )


class IsAuthenticatedWallet(BasePermission):
    """
    Require a wallet proven by a valid auth token.

    WalletAuthentication returns a wallet whenever a `wallet-hash` header is
    present, and only sets `is_authenticated` when a token accompanies it. On an
    endpoint that mints credentials we want the stronger check -- otherwise
    anyone who knows a wallet hash could mint a key for it.
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and getattr(user, 'is_authenticated', False)
            and getattr(user, 'wallet_hash', None)
        )


class LookupKeyAuthentication(BaseAuthentication):
    """
    Authenticate via the X-Api-Key header.

    Returns (lookup_key_instance, raw_key). Raises AuthenticationFailed when
    the header is missing or the key is unknown -- a revoked key is simply
    absent from the table.
    """

    def authenticate(self, request):
        raw_key = get_lookup_key_from_request(request)

        if not raw_key:
            return None

        lookup_key = resolve_key(raw_key)

        if not lookup_key:
            raise AuthenticationFailed('Invalid lookup key')

        return (lookup_key, raw_key)

    def authenticate_header(self, request):
        # Makes DRF respond 401 rather than 403.
        return 'X-Api-Key'


class WalletLookupKeyBaseView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [WalletLookupKeyThrottle]


class WalletLookupKeyView(WalletLookupKeyBaseView):
    """
    Mint or revoke the single lookup key belonging to the authenticated wallet.
    """

    authentication_classes = [WalletAuthentication]
    permission_classes = [IsAuthenticatedWallet]

    @swagger_auto_schema(
        operation_description=(
            "Mint a lookup key for the authenticated wallet. The raw key is "
            "returned exactly once and cannot be retrieved again. One key per "
            "wallet: if the wallet already has one this returns 409 and the "
            "existing key keeps working."
        ),
        request_body=WalletLookupKeyCreateSerializer,
        responses={201: WalletLookupKeyCreatedSerializer},
    )
    def post(self, request, *args, **kwargs):
        wallet = request.user

        # Check first so the common case returns a clear error, and so an
        # existing key is never silently rotated out from under the caller.
        if WalletLookupKey.objects.filter(wallet=wallet).exists():
            return Response(
                {
                    'error': 'lookup_key_already_exists',
                    'detail': (
                        'This wallet already has a lookup key. Revoke it with '
                        'DELETE /api/wallet/lookup-keys/ before minting a new one.'
                    ),
                },
                status=status.HTTP_409_CONFLICT
            )

        raw_key = generate_raw_key()

        serializer = WalletLookupKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Bind to the authenticated wallet, never to whatever the body says.
        try:
            instance = serializer.save(
                wallet=wallet,
                key_hash=hash_key(raw_key),
            )
        except IntegrityError:
            # Backstop for two concurrent mints racing on the one-to-one
            # constraint.
            return Response(
                {'error': 'lookup_key_already_exists'},
                status=status.HTTP_409_CONFLICT
            )

        response_serializer = WalletLookupKeyCreatedSerializer(
            instance, context={'lookup_key': raw_key}
        )
        data = dict(response_serializer.data)
        data['lookup_key'] = raw_key

        return Response(data, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(
        operation_description=(
            "Revoke (hard delete) the authenticated wallet's lookup key. "
            "Returns 404 if the wallet has no key, so a blind "
            "DELETE-then-POST rotation sequence is safe to retry."
        ),
        responses={204: None, 404: None},
    )
    def delete(self, request, *args, **kwargs):
        wallet = request.user

        try:
            instance = WalletLookupKey.objects.get(wallet=wallet)
        except WalletLookupKey.DoesNotExist:
            return Response(
                {'error': 'no_lookup_key'},
                status=status.HTTP_404_NOT_FOUND
            )

        wallet_hash = wallet.wallet_hash
        instance.delete()

        # Drop the cached balances so the next read reflects the wallet as it
        # is now, not as it was.
        self._clear_wallet_cache(wallet_hash)

        return Response(status=status.HTTP_204_NO_CONTENT)

    def _clear_wallet_cache(self, wallet_hash):
        cache = settings.REDISKV
        try:
            # Only the BCH and per-category keys matter here; scan_keys avoids
            # blocking Redis with KEYS.
            from main.utils.cache import scan_keys
            keys = scan_keys(cache, f'wallet:balance:*:{wallet_hash}*')
            if keys:
                cache.delete(*keys)
        except Exception as exc:
            # A cache failure must not fail the revocation.
            logger.warning(
                f'Failed to clear balance cache for {wallet_hash}: {exc}'
            )


class WalletLookupKeyBalanceView(WalletLookupKeyBaseView):
    """
    Read a wallet's BCH and CashToken balances using a lookup key.
    """

    authentication_classes = [LookupKeyAuthentication]

    @swagger_auto_schema(
        operation_description=(
            "Resolve an X-Api-Key header to a wallet and return its BCH and "
            "CashToken balances. The BCH balance is always returned in the "
            "`bch` field; `assets` only adds CashTokens on top of it. SLP "
            "assets are not supported."
        ),
        manual_parameters=[
            openapi.Parameter(
                name='assets',
                type=openapi.TYPE_STRING,
                in_=openapi.IN_QUERY,
                required=False,
                description=(
                    "Optional comma-separated CashToken ids: "
                    "'ct/<category>' or 'ct/<category>/<txid>/<index>'. Omit "
                    "for BCH only. The BCH balance never needs to be listed "
                    "here -- it is always in the `bch` field, and passing "
                    "'bch' is rejected. Max 20 assets per request."
                ),
            ),
        ],
        responses={200: WalletLookupKeyBalanceSerializer},
    )
    def get(self, request, *args, **kwargs):
        lookup_key = request.user
        wallet = lookup_key.wallet

        assets_param = request.query_params.get('assets', '')
        asset_ids = parse_assets_param(assets_param)

        try:
            data = get_wallet_balances(wallet, asset_ids)
        except InvalidAssetId as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Track usage on the key, not on the wallet -- this avoids a write on
        # the wallet row for every read of a hot key.
        lookup_key.last_used_at = timezone.now()
        lookup_key.save(update_fields=['last_used_at'])

        return Response(data, status=status.HTTP_200_OK)
