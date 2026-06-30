import logging

from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated


logger = logging.getLogger(__name__)
from drf_yasg.utils import swagger_auto_schema
from .serializers import (
    PubkeyRegisterSerializer,
    PubkeyUnregisterSerializer,
    PubkeyLastOnlineSerializer,
    PubkeyTouchSerializer,
    ShowActiveStatusSerializer,
    WalletHashSerializer,
    RoomSerializer,
    RoomCreateSerializer,
    RoomUpdateSerializer,
    RoomBatchSyncSerializer,
    BlockContactSerializer,
    BlockGroupSerializer,
)
from .authentication import BitcoinCashOAuthAuthentication
from .models import NostrPubkey, NostrRoom, NostrBlockedContact, NostrBlockedGroup
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
    """
    authentication_classes = [BitcoinCashOAuthAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = PubkeyLastOnlineSerializer

    @swagger_auto_schema(
        request_body=PubkeyLastOnlineSerializer,
        responses={200: PubkeyLastOnlineSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        pubkeys = serializer.validated_data['pubkeys']

        # Check if the requester has opted out of seeing others' status.
        from main.models import Address
        user_address = getattr(request.user, 'bitcoincash_address', None)
        if user_address:
            wallet_hashes = Address.objects.filter(
                address=user_address,
            ).values_list('wallet__wallet_hash', flat=True)
            requester_blocked = NostrPubkey.objects.filter(
                wallet_hash__in=wallet_hashes,
                show_active_status=False,
            ).exists()
            if requester_blocked:
                return Response({pk: None for pk in pubkeys})

        status_map = {
            np['pubkey_hex']: np['show_active_status']
            for np in NostrPubkey.objects.filter(
                pubkey_hex__in=pubkeys,
            ).values('pubkey_hex', 'show_active_status')
        }

        result = {}
        uncached_pubkeys = []

        for pubkey in pubkeys:
            show = status_map.get(pubkey)
            if show is False:
                result[pubkey] = None
                continue
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
    permission_classes = [IsAuthenticated]
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

        from .utils.auth import verify_wallet_ownership
        ok, reason = verify_wallet_ownership(request.user, np_sender.wallet_hash)
        if not ok:
            return Response({"error": reason}, status=status.HTTP_403_FORBIDDEN)

        now = timezone.now()

        if np_sender.show_active_status:
            NostrPubkey.objects.filter(pk=np_sender.pk).update(last_active=now)
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
                else:
                    logger.info(
                        f'Touch: recipient {recipient_pubkey[:16]}... not found '
                        f'in NostrPubkey — skipping WS push'
                    )

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


class ShowActiveStatusView(APIView):
    """Toggle whether the user's active status is visible to others."""
    authentication_classes = [BitcoinCashOAuthAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = ShowActiveStatusSerializer

    @swagger_auto_schema(
        request_body=ShowActiveStatusSerializer,
        responses={200: "updated"},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        wallet_hash = serializer.validated_data['wallet_hash']
        show_active_status = serializer.validated_data['show_active_status']

        from .utils.auth import verify_wallet_ownership
        ok, reason = verify_wallet_ownership(request.user, wallet_hash)
        if not ok:
            return Response({"error": reason}, status=status.HTTP_403_FORBIDDEN)

        updated = NostrPubkey.objects.filter(wallet_hash=wallet_hash).update(
            show_active_status=show_active_status,
        )
        if not updated:
            return Response(
                {"error": "NostrPubkey not found for this wallet_hash"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            "status": "updated",
            "show_active_status": show_active_status,
        }, status=status.HTTP_200_OK)


class NostrRoomListView(APIView):
    """List rooms for a wallet or create a new room."""
    authentication_classes = [BitcoinCashOAuthAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        wallet_hash = request.query_params.get('wallet_hash')
        if not wallet_hash:
            return Response(
                {"error": "wallet_hash query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from .utils.auth import verify_wallet_ownership
        ok, reason = verify_wallet_ownership(request.user, wallet_hash)
        if not ok:
            return Response({"error": reason}, status=status.HTTP_403_FORBIDDEN)

        from django.db.models import Case, When, Value, BooleanField
        rooms = NostrRoom.objects.filter(wallet_hash=wallet_hash).annotate(
            has_msg=Case(
                When(last_message_timestamp__isnull=False, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        ).order_by('-has_msg', '-last_message_timestamp')
        serializer = RoomSerializer(rooms, many=True)
        return Response({"rooms": serializer.data})

    def post(self, request, *args, **kwargs):
        serializer = RoomCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        wallet_hash = serializer.validated_data['wallet_hash']
        room_data = serializer.validated_data['room']

        from .utils.auth import verify_wallet_ownership
        ok, reason = verify_wallet_ownership(request.user, wallet_hash)
        if not ok:
            return Response({"error": reason}, status=status.HTTP_403_FORBIDDEN)

        NostrRoom.objects.update_or_create(
            wallet_hash=wallet_hash,
            room_id=room_data['room_id'],
            defaults={
                'type': room_data['type'],
                'name': room_data['name'],
                'members': room_data['members'],
                'subject': room_data.get('subject'),
                'avatar': room_data.get('avatar'),
                'created_at': room_data['created_at'],
                'updated_at': room_data['updated_at'],
                'archived': room_data.get('archived', False),
            },
        )
        return Response({"status": "created"}, status=status.HTTP_201_CREATED)


class NostrRoomDetailView(APIView):
    """Update or delete a specific room."""
    authentication_classes = [BitcoinCashOAuthAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, room_id, *args, **kwargs):
        serializer = RoomUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        wallet_hash = serializer.validated_data['wallet_hash']

        from .utils.auth import verify_wallet_ownership
        ok, reason = verify_wallet_ownership(request.user, wallet_hash)
        if not ok:
            return Response({"error": reason}, status=status.HTTP_403_FORBIDDEN)

        room = NostrRoom.objects.filter(
            wallet_hash=wallet_hash, room_id=room_id,
        ).first()
        if not room:
            return Response(
                {"error": "Room not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        update_fields = {}
        for field in ('name', 'subject', 'archived'):
            if field in serializer.validated_data:
                update_fields[field] = serializer.validated_data[field]
        update_fields['updated_at'] = timezone.now()

        NostrRoom.objects.filter(
            wallet_hash=wallet_hash, room_id=room_id,
        ).update(**update_fields)

        return Response({"status": "updated"})

    def delete(self, request, room_id, *args, **kwargs):
        serializer = WalletHashSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        wallet_hash = serializer.validated_data['wallet_hash']

        from .utils.auth import verify_wallet_ownership
        ok, reason = verify_wallet_ownership(request.user, wallet_hash)
        if not ok:
            return Response({"error": reason}, status=status.HTTP_403_FORBIDDEN)

        deleted = NostrRoom.objects.filter(
            wallet_hash=wallet_hash, room_id=room_id,
        ).delete()[0]

        if not deleted:
            return Response(
                {"error": "Room not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"status": "deleted"})


class NostrRoomBatchSyncView(APIView):
    """Bulk upsert rooms for a wallet."""
    authentication_classes = [BitcoinCashOAuthAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = RoomBatchSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        wallet_hash = serializer.validated_data['wallet_hash']
        rooms = serializer.validated_data['rooms']

        from .utils.auth import verify_wallet_ownership
        ok, reason = verify_wallet_ownership(request.user, wallet_hash)
        if not ok:
            return Response({"error": reason}, status=status.HTTP_403_FORBIDDEN)

        synced = []
        for room_data in rooms:
            NostrRoom.objects.update_or_create(
                wallet_hash=wallet_hash,
                room_id=room_data['room_id'],
                defaults={
                    'type': room_data['type'],
                    'name': room_data['name'],
                    'members': room_data['members'],
                    'subject': room_data.get('subject'),
                    'avatar': room_data.get('avatar'),
                    'created_at': room_data['created_at'],
                    'updated_at': room_data['updated_at'],
                    'archived': room_data.get('archived', False),
                },
            )
            synced.append(room_data['room_id'])

        return Response({
            "status": "synced",
            "rooms": synced,
        })


class NostrBlockListView(APIView):
    """List blocked contacts and groups for a wallet."""
    authentication_classes = [BitcoinCashOAuthAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        wallet_hash = request.query_params.get('wallet_hash')
        if not wallet_hash:
            return Response(
                {"error": "wallet_hash query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from .utils.auth import verify_wallet_ownership
        ok, reason = verify_wallet_ownership(request.user, wallet_hash)
        if not ok:
            return Response({"error": reason}, status=status.HTTP_403_FORBIDDEN)

        blocked_contacts = list(
            NostrBlockedContact.objects.filter(
                wallet_hash=wallet_hash,
            ).values_list('pub_key_hex', flat=True)
        )
        blocked_groups = list(
            NostrBlockedGroup.objects.filter(
                wallet_hash=wallet_hash,
            ).values_list('room_id', flat=True)
        )
        return Response({
            "blocked_contacts": blocked_contacts,
            "blocked_groups": blocked_groups,
        })


class NostrBlockContactView(APIView):
    """Block or unblock a contact."""
    authentication_classes = [BitcoinCashOAuthAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = BlockContactSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        wallet_hash = serializer.validated_data['wallet_hash']
        pub_key_hex = serializer.validated_data['pub_key_hex']

        from .utils.auth import verify_wallet_ownership
        ok, reason = verify_wallet_ownership(request.user, wallet_hash)
        if not ok:
            return Response({"error": reason}, status=status.HTTP_403_FORBIDDEN)

        NostrBlockedContact.objects.get_or_create(
            wallet_hash=wallet_hash,
            pub_key_hex=pub_key_hex,
        )
        return Response({"status": "blocked"})

    def delete(self, request, pub_key_hex, *args, **kwargs):
        serializer = WalletHashSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        wallet_hash = serializer.validated_data['wallet_hash']

        from .utils.auth import verify_wallet_ownership
        ok, reason = verify_wallet_ownership(request.user, wallet_hash)
        if not ok:
            return Response({"error": reason}, status=status.HTTP_403_FORBIDDEN)

        deleted = NostrBlockedContact.objects.filter(
            wallet_hash=wallet_hash,
            pub_key_hex=pub_key_hex,
        ).delete()[0]

        if not deleted:
            return Response(
                {"error": "Contact not found in blocked list"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"status": "unblocked"})


class NostrBlockGroupView(APIView):
    """Block or unblock a group."""
    authentication_classes = [BitcoinCashOAuthAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = BlockGroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        wallet_hash = serializer.validated_data['wallet_hash']
        room_id = serializer.validated_data['room_id']

        from .utils.auth import verify_wallet_ownership
        ok, reason = verify_wallet_ownership(request.user, wallet_hash)
        if not ok:
            return Response({"error": reason}, status=status.HTTP_403_FORBIDDEN)

        NostrBlockedGroup.objects.get_or_create(
            wallet_hash=wallet_hash,
            room_id=room_id,
        )
        return Response({"status": "blocked"})

    def delete(self, request, room_id, *args, **kwargs):
        serializer = WalletHashSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        wallet_hash = serializer.validated_data['wallet_hash']

        from .utils.auth import verify_wallet_ownership
        ok, reason = verify_wallet_ownership(request.user, wallet_hash)
        if not ok:
            return Response({"error": reason}, status=status.HTTP_403_FORBIDDEN)

        deleted = NostrBlockedGroup.objects.filter(
            wallet_hash=wallet_hash,
            room_id=room_id,
        ).delete()[0]

        if not deleted:
            return Response(
                {"error": "Group not found in blocked list"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"status": "unblocked"})
