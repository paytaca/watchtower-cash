from django.db.models import Q
from django.utils import timezone
from django.db import transaction
from rest_framework import serializers
from push_notifications.models import GCMDevice, APNSDevice

from .models import DeviceWallet


class DeviceWalletSerializer(serializers.ModelSerializer):
    gcm_registration_id = serializers.CharField(source="gcm_device.registration_id", read_only=True)
    apns_registration_id = serializers.CharField(source="apns_device.registration_id", read_only=True)

    class Meta:
        model = DeviceWallet
        fields = [
            "id",
            "wallet_hash",
            "multi_wallet_index",
            "last_active",

            "gcm_registration_id",
            "apns_registration_id",
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
    multi_wallet_index = serializers.IntegerField(required=False)
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
        self.sync_device_wallet_hashes(
            gcm_device,
            validated_data["wallet_hashes"],
            multi_wallet_index=validated_data.get("multi_wallet_index"),
        )
        return gcm_device

    @transaction.atomic
    def save_apns_device(self, apns_device_data, validated_data):
        registration_id = apns_device_data.pop("registration_id") # don't add a default value, it MUST exist
        apns_device_data["active"] = True
        apns_device, created = APNSDevice.objects.update_or_create(
            registration_id=registration_id,
            defaults=apns_device_data
        )
        self.sync_device_wallet_hashes(
            apns_device,
            validated_data["wallet_hashes"],
            multi_wallet_index=validated_data.get("multi_wallet_index"),
        )
        return apns_device

    def sync_device_wallet_hashes(self, device, wallet_hashes, multi_wallet_index=None):
        if not isinstance(device, GCMDevice) and not isinstance(device, APNSDevice):
            raise serializers.ValidationError("invalid device type")

        device_wallets = []
        now = timezone.now()
        for wallet_hash in wallet_hashes:
            filter_kwargs = { "wallet_hash": wallet_hash, "multi_wallet_index": multi_wallet_index }
            if isinstance(device, GCMDevice):
                filter_kwargs["gcm_device"] = device
            elif isinstance(device, APNSDevice):
                filter_kwargs["apns_device"] = device

            device_wallet, _ = DeviceWallet.objects.update_or_create(
                **filter_kwargs,
                defaults={ "last_active": now },
            )
            device_wallets.append(device_wallet)

        device.device_wallets.filter(multi_wallet_index=multi_wallet_index).exclude(
            wallet_hash__in=wallet_hashes
        ).delete()

        # this device wallet context maintained before multi wallet index is added
        if isinstance(multi_wallet_index, int):
            device.device_wallets.filter(multi_wallet_index=None).delete()

        return device_wallets


class DeviceUnsubscribeSerializer(serializers.Serializer):
    gcm_device_id = serializers.IntegerField(required=False, write_only=True)
    apns_device_id = serializers.CharField(required=False, write_only=True)
    application_id = serializers.CharField(required=False, write_only=True)
    wallet_hashes = serializers.ListSerializer(
        child=serializers.CharField(),
        required=True, write_only=True,
    )

    @transaction.atomic
    def unsubscribe_devices(self, device_obj_qs, wallet_hashes):
        filter_kwargs = { "wallet_hash__in": wallet_hashes }

        device_ids = device_obj_qs.values_list("id", flat=True).distinct()
        if device_obj_qs.model == GCMDevice:
            filter_kwargs["gcm_device_id__in"] = device_ids
        elif device_obj_qs.model == APNSDevice:
            filter_kwargs["apns_device_id__in"] = device_ids
        else:
            raise serializers.ValidationError("No GCM or APNS device object specified")

        device_wallets = DeviceWallet.objects.filter(**filter_kwargs)
        device_wallets_data = [*device_wallets.values()]        
        device_wallets.delete()

        devices_to_delete = device_obj_qs.filter(device_wallets__isnull=True)
        if devices_to_delete.count():
            # deleted_devices_data = devices_to_delete.distinct().values("registration_id", "device_id")
            devices_to_delete.delete()

        return device_wallets_data

    def save(self):
        validated_data = self.validated_data

        app_id = validated_data.get("application_id")

        device_wallets_data = []
        if "gcm_device_id" in validated_data:
            gcm_device_qs = GCMDevice.objects.filter(device_id=validated_data["gcm_device_id"])
            if app_id: gcm_device_qs = gcm_device_qs.filter(application_id=app_id)

            device_wallets_data += self.unsubscribe_devices(
                gcm_device_qs, validated_data["wallet_hashes"],
            )

        if "apns_device_id" in validated_data:
            apns_device_qs = APNSDevice.objects.filter(device_id=validated_data["apns_device_id"])
            if app_id: apns_device_qs = apns_device_qs.filter(application_id=app_id)

            device_wallets_data += self.unsubscribe_devices(
                apns_device_qs, validated_data["wallet_hashes"],
            )

        return device_wallets_data
