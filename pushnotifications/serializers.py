from django.utils import timezone
from django.db import transaction
from rest_framework import serializers
from push_notifications.models import GCMDevice, APNSDevice

from .models import DeviceWallet


class DeviceWalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceWallet
        fields = [
            "id",
            "wallet_hash",
            "last_active",
        ]


class GCMDeviceSerializer(serializers.ModelSerializer):
    device_wallets = DeviceWalletSerializer(many=True, read_only=True)

    class Meta:
        model = GCMDevice
        fields = [
            "id",
            "name",
            "active",
            "date_created",
            "application_id",
            "device_id",
            "registration_id",
            "cloud_message_type",
            "device_wallets",
        ]

        extra_kwargs = {
            "device_id": {
                "required": True,
            },
            "date_created": {
                "read_only": True,
            },
            "cloud_message_type": {
                "read_only": True,
            },
        }


class APNSDeviceSerializer(serializers.ModelSerializer):
    device_wallets = DeviceWalletSerializer(many=True, read_only=True)

    class Meta:
        model = APNSDevice
        fields = [
            "id",
            "name",
            "active",
            "date_created",
            "application_id",
            "device_id",
            "registration_id",
            "device_wallets",
        ]

        extra_kwargs = {
            "device_id": {
                "required": True,
            },
            "date_created": {
                "read_only": True,
            },
        }


class DeviceSubscriptionSerializer(serializers.Serializer):
    gcm_device = GCMDeviceSerializer(required=False)
    apns_device = APNSDeviceSerializer(required=False)
    wallet_hashes = serializers.ListSerializer(
        child=serializers.CharField(),
        required=True,
        write_only=True,
    )

    def validate(self, data):
        if "gcm_device" not in data and "apns_device" not in data:
            raise serializers.ValidationError(f"'gcm_device' or 'apns_device' must be provided")
        return data

    def save(self):
        validated_data = self.validated_data
        instance = {}
        if "gcm_device" in validated_data:
            gcm_device_data = validated_data.pop("gcm_device", None)
            instance["gcm_device"] = self.save_gcm_device(gcm_device_data, validated_data)
        elif "apns_device" in validated_data:
            apns_device_data = validated_data.pop("apns_device", None)
            instance["apns_device"] = self.save_apns_device(apns_device_data, validated_data)
        else:
            raise serializers.ValidationError("missing device data")

        self.instance = instance
        return self.instance

    @transaction.atomic
    def save_gcm_device(self, gcm_device_data, validated_data):
        registration_id = gcm_device_data.pop("registration_id") # don't add a default value, it MUST exist
        gcm_device_data["active"] = True
        gcm_device_data["cloud_message_type"] = "FCM"
        gcm_device, created = GCMDevice.objects.update_or_create(
            registration_id=registration_id,
            defaults=gcm_device_data,
        )
        self.sync_device_wallet_hashes(gcm_device, validated_data["wallet_hashes"])
        return gcm_device

    @transaction.atomic
    def save_apns_device(self, apns_device_data, validated_data):
        registration_id = apns_device_data.pop("registration_id") # don't add a default value, it MUST exist
        apns_device_data["active"] = True
        apns_device, created = APNSDevice.objects.update_or_create(
            registration_id=registration_id,
            defaults=apns_device_data
        )
        self.sync_device_wallet_hashes(apns_device, validated_data["wallet_hashes"])
        return apns_device

    def sync_device_wallet_hashes(self, device, wallet_hashes):
        if not isinstance(device, GCMDevice) and not isinstance(device, APNSDevice):
            raise serializers.ValidationError("invalid device type")

        device_wallets = []
        now = timezone.now()
        for wallet_hash in wallet_hashes:
            filter_kwargs = { "wallet_hash": wallet_hash }
            if isinstance(device, GCMDevice):
                filter_kwargs["gcm_device"] = device
            elif isinstance(device, APNSDevice):
                filter_kwargs["gcm_device"] = device

            device_wallet, _ = DeviceWallet.objects.update_or_create(
                **filter_kwargs,
                defaults={ "last_active": now },
            )
            device_wallets.append(device_wallet)

        device.device_wallets.exclude(
            wallet_hash__in=wallet_hashes
        ).delete()

        return device_wallets
