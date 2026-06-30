from django.utils import timezone
from rest_framework import serializers
from .models import NostrPubkey, NostrRoom, NostrBlockedContact, NostrBlockedGroup
from main.utils.cache import set_last_active
from nostr.utils.websocket import send_last_active_update


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


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = NostrRoom
        fields = ('room_id', 'type', 'name', 'members', 'subject',
                  'avatar', 'created_at', 'updated_at',
                  'last_message_timestamp', 'archived')


class RoomCreateSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(max_length=70)
    room = RoomSerializer()


class RoomUpdateSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(max_length=70)
    name = serializers.CharField(max_length=255, required=False)
    subject = serializers.CharField(allow_null=True, required=False)
    archived = serializers.BooleanField(required=False)


class RoomDeleteSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(max_length=70)


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


class BlockGroupSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(max_length=70)
    room_id = serializers.CharField(max_length=128)
