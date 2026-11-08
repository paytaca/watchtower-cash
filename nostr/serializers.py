from django.utils import timezone
from rest_framework import serializers
from .models import NostrPubkey, NostrRoom, NostrBlockedContact, NostrBlockedGroup
from main.utils.cache import set_last_active
from nostr.utils.websocket import send_last_active_update
from nostr.utils.rooms import room_push_token


import re

class PubkeyRegisterSerializer(serializers.Serializer):
    pubkey = serializers.CharField(max_length=64)
    wallet_hash = serializers.CharField(max_length=70)

    def validate_pubkey(self, value):
        if not re.match(r'^[0-9a-fA-F]{64}$', value):
            raise serializers.ValidationError("pubkey must be a 64-character hex string.")
        return value.lower()

    def save(self):
        validated_data = self.validated_data
        pubkey = validated_data['pubkey']
        wallet_hash = validated_data['wallet_hash']

        nostr_pubkey, _ = NostrPubkey.objects.update_or_create(
            wallet_hash=wallet_hash,
            defaults={
                'pubkey_hex': pubkey,
            },
        )

        if nostr_pubkey.show_active_status:
            now = timezone.now()
            NostrPubkey.objects.filter(pk=nostr_pubkey.pk).update(last_active=now)
            set_last_active(pubkey, now)
            send_last_active_update(wallet_hash, pubkey, now)

        return nostr_pubkey


MAX_PUBKEYS = 500


class PubkeyLastOnlineSerializer(serializers.Serializer):
    pubkeys = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=False,
        max_length=MAX_PUBKEYS,
    )

    def validate_pubkeys(self, value):
        for pubkey in value:
            if not re.match(r'^[0-9a-fA-F]{64}$', pubkey):
                raise serializers.ValidationError(
                    f"'{pubkey}' is not a valid 64-character hex string."
                )
        return [p.lower() for p in value]


class PubkeyTouchSerializer(serializers.Serializer):
    pubkey = serializers.CharField(max_length=64)
    recipients = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=True,
        max_length=MAX_PUBKEYS,
    )

    def validate_pubkey(self, value):
        if not re.match(r'^[0-9a-fA-F]{64}$', value):
            raise serializers.ValidationError("pubkey must be a 64-character hex string.")
        return value.lower()

    def validate_recipients(self, value):
        for pubkey in value:
            if not re.match(r'^[0-9a-fA-F]{64}$', pubkey):
                raise serializers.ValidationError(
                    f"'{pubkey}' is not a valid 64-character hex string."
                )
        return [p.lower() for p in value]


class ShowActiveStatusSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(max_length=70)
    show_active_status = serializers.BooleanField(required=True)


class PubkeyUnregisterSerializer(serializers.Serializer):
    pubkey = serializers.CharField(max_length=64)

    def validate_pubkey(self, value):
        if not re.match(r'^[0-9a-fA-F]{64}$', value):
            raise serializers.ValidationError("pubkey must be a 64-character hex string.")
        return value.lower()

    def save(self):
        validated_data = self.validated_data
        pubkey = validated_data['pubkey']

        deleted = NostrPubkey.objects.filter(pubkey_hex=pubkey).delete()
        return deleted[0] or 0


class WalletHashSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(max_length=70)


class RoomRolesValidationMixin:
    """Validates the MLS role mirror (``owner`` / ``admins``).

    Roles are claimed by the client and the server does not verify the claim:
    clients authorize role changes against the MLS ratchet tree, so a forged
    value here cannot grant control of a group.

    Update verbs for the mirror: omitting a key preserves the stored value,
    ``owner: null`` clears the owner, and ``admins: []`` clears the admin list.
    ``admins: null`` is rejected so the JSON column always holds a list.
    """

    def validate_owner(self, value):
        # ``None`` is the explicit "clear the owner" verb; an omitted key
        # preserves the stored owner.
        if value is None:
            return value
        if not re.match(r'^[0-9a-fA-F]{64}$', value):
            raise serializers.ValidationError(
                "owner must be a 64-character hex string."
            )
        return value.lower()

    def validate_admins(self, value):
        # ``[]`` is the clear verb. The field rejects ``null`` so the column
        # keeps its list shape; an omitted key preserves the stored list.
        cleaned = []
        for admin in value:
            if not isinstance(admin, str):
                raise serializers.ValidationError(
                    f"admin {admin!r} is not a string."
                )
            if not re.match(r'^[0-9a-fA-F]{64}$', admin):
                raise serializers.ValidationError(
                    f"admin '{admin}' is not a 64-character hex string."
                )
            cleaned.append(admin.lower())
        # Order-preserving dedupe: the client resends the full list on every
        # role change and a promotion may be announced twice.
        return list(dict.fromkeys(cleaned))


class RoomSerializer(RoomRolesValidationMixin, serializers.ModelSerializer):
    nostr_group_id = serializers.CharField(
        max_length=64,
        allow_null=True,
        required=False,
    )
    owner = serializers.CharField(
        max_length=64,
        allow_null=True,
        required=False,
    )
    admins = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=True,
        required=False,
    )
    # Read-only, derived from room_id. Clients put it on outbound gift-wraps so
    # the relay watcher can skip pushes for a muted conversation without the
    # relay learning the room id.
    push_token = serializers.SerializerMethodField()

    class Meta:
        model = NostrRoom
        fields = ('room_id', 'type', 'name', 'members', 'nostr_group_id', 'subject',
                  'avatar', 'created_at', 'updated_at',
                  'last_message_timestamp', 'archived', 'muted', 'owner',
                  'admins', 'push_token')

    def get_push_token(self, room):
        return room_push_token(room.room_id)

    def validate_nostr_group_id(self, value):
        if value is None:
            return value
        if not re.match(r'^[0-9a-fA-F]{64}$', value):
            raise serializers.ValidationError(
                "nostr_group_id must be a 64-character hex string."
            )
        return value.lower()

    def validate_members(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("members must be a list.")
        cleaned = []
        for member in value:
            if not isinstance(member, str):
                raise serializers.ValidationError(
                    f"member {member!r} is not a string."
                )
            if not re.match(r'^[0-9a-fA-F]{64}$', member):
                raise serializers.ValidationError(
                    f"member '{member}' is not a 64-character hex string."
                )
            cleaned.append(member.lower())
        return cleaned


class RoomCreateSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(max_length=70)
    room = RoomSerializer()


class RoomUpdateSerializer(RoomRolesValidationMixin, serializers.Serializer):
    wallet_hash = serializers.CharField(max_length=70)
    name = serializers.CharField(max_length=255, required=False)
    subject = serializers.CharField(allow_null=True, required=False)
    archived = serializers.BooleanField(required=False)
    muted = serializers.BooleanField(required=False)
    nostr_group_id = serializers.CharField(max_length=64, allow_null=True, required=False)
    members = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=True,
        required=False,
    )
    owner = serializers.CharField(max_length=64, allow_null=True, required=False)
    admins = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=True,
        required=False,
    )

    def validate_nostr_group_id(self, value):
        if value is None:
            return value
        if not re.match(r'^[0-9a-fA-F]{64}$', value):
            raise serializers.ValidationError(
                "nostr_group_id must be a 64-character hex string."
            )
        return value.lower()

    def validate_members(self, value):
        cleaned = []
        for member in value:
            if not isinstance(member, str):
                raise serializers.ValidationError(
                    f"member {member!r} is not a string."
                )
            if not re.match(r'^[0-9a-fA-F]{64}$', member):
                raise serializers.ValidationError(
                    f"member '{member}' is not a 64-character hex string."
                )
            cleaned.append(member.lower())
        return cleaned


class RoomBatchSyncSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(max_length=70)
    rooms = RoomSerializer(many=True)


class BlockContactSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(max_length=70)
    pub_key_hex = serializers.CharField(max_length=64)

    def validate_pub_key_hex(self, value):
        if not re.match(r'^[0-9a-fA-F]{64}$', value):
            raise serializers.ValidationError("pub_key_hex must be a 64-character hex string.")
        return value.lower()


class RoomTouchSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(max_length=70)
    timestamp = serializers.DateTimeField(required=False)


class BlockGroupSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(max_length=70)
    room_id = serializers.CharField(max_length=128)
