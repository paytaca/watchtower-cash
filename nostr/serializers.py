from django.utils import timezone
from rest_framework import serializers
from .models import NostrPubkey


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
                'last_active': timezone.now(),
            },
        )

        return nostr_pubkey


class PubkeyLastOnlineSerializer(serializers.Serializer):
    pubkeys = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=False,
    )

    def validate_pubkeys(self, value):
        for pubkey in value:
            if not re.match(r'^[0-9a-fA-F]{64}$', pubkey):
                raise serializers.ValidationError(
                    f"'{pubkey}' is not a valid 64-character hex string."
                )
        return [p.lower() for p in value]


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
