from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from push_notifications.models import GCMDevice, APNSDevice
from .models import NostrPubkeyDevice


import re

class PushRegisterSerializer(serializers.Serializer):
    pubkey = serializers.CharField(max_length=64)
    wallet_hash = serializers.CharField(max_length=70)
    multi_wallet_index = serializers.IntegerField(required=False, allow_null=True)
    registration_id = serializers.CharField()
    device_id = serializers.CharField()
    platform = serializers.ChoiceField(choices=[('android', 'Android'), ('ios', 'iOS')])

    def validate_pubkey(self, value):
        if not re.match(r'^[0-9a-fA-F]{64}$', value):
            raise serializers.ValidationError("pubkey must be a 64-character hex string.")
        return value.lower()

    @transaction.atomic
    def save(self):
        validated_data = self.validated_data
        pubkey = validated_data['pubkey']
        wallet_hash = validated_data['wallet_hash']
        multi_wallet_index = validated_data.get('multi_wallet_index')
        registration_id = validated_data['registration_id']
        device_id = validated_data['device_id']
        platform = validated_data['platform']

        # iOS device IDs are UUIDs with dashes; HexIntegerField can't parse dashes.
        # Strip dashes so the value is a plain hex string (32 chars).
        if platform == 'ios' and isinstance(device_id, str):
            device_id = device_id.replace('-', '').upper()

        # Upsert the device record in the existing push_notifications tables
        if platform == 'android':
            device, _ = GCMDevice.objects.update_or_create(
                registration_id=registration_id,
                defaults={
                    'device_id': device_id,
                    'active': True,
                    'cloud_message_type': 'FCM',
                },
            )
            # Remove any existing APNS link for this pubkey+device combo
            NostrPubkeyDevice.objects.filter(
                pubkey_hex=pubkey,
                apns_device__device_id=device_id,
            ).delete()
            nostr_device, _ = NostrPubkeyDevice.objects.update_or_create(
                pubkey_hex=pubkey,
                gcm_device=device,
                defaults={
                    'wallet_hash': wallet_hash,
                    'multi_wallet_index': multi_wallet_index,
                    'last_active': timezone.now(),
                },
            )
        else:
            device, _ = APNSDevice.objects.update_or_create(
                registration_id=registration_id,
                defaults={
                    'device_id': device_id,
                    'active': True,
                },
            )
            # Remove any existing GCM link for this pubkey+device combo
            NostrPubkeyDevice.objects.filter(
                pubkey_hex=pubkey,
                gcm_device__device_id=device_id,
            ).delete()
            nostr_device, _ = NostrPubkeyDevice.objects.update_or_create(
                pubkey_hex=pubkey,
                apns_device=device,
                defaults={
                    'wallet_hash': wallet_hash,
                    'multi_wallet_index': multi_wallet_index,
                    'last_active': timezone.now(),
                },
            )

        return nostr_device


class PushUnregisterSerializer(serializers.Serializer):
    pubkey = serializers.CharField(max_length=64)
    device_id = serializers.CharField()

    @transaction.atomic
    def save(self):
        validated_data = self.validated_data
        pubkey = validated_data['pubkey']
        device_id = validated_data['device_id']

        # Delete matching NostrPubkeyDevice rows for this pubkey + device_id
        # We match across both GCM and APNS devices
        gcm_deleted = NostrPubkeyDevice.objects.filter(
            pubkey_hex=pubkey,
            gcm_device__device_id=device_id,
        ).delete()
        apns_deleted = NostrPubkeyDevice.objects.filter(
            pubkey_hex=pubkey,
            apns_device__device_id=device_id,
        ).delete()

        # Return total count of deleted records for consistency
        return (gcm_deleted[0] or 0) + (apns_deleted[0] or 0)
