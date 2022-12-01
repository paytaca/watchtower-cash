import json
import pytz
from uuid import uuid4
from datetime import datetime
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import (
    LinkedDeviceInfo,
    PosDevice,
    Location,
    Merchant,
    Branch,
)
from .utils.broadcast import broadcast_transaction
from .utils.totp import generate_pos_device_totp
from .utils.websocket import send_device_update


REDIS_CLIENT = settings.REDISKV


class TimestampField(serializers.IntegerField):
    def to_representation(self, value):
        return datetime.timestamp(value)

    def to_internal_value(self, data):
        return datetime.fromtimestamp(data).replace(tzinfo=pytz.UTC)


class PosDeviceLinkSerializer(serializers.Serializer):
    code = serializers.CharField()
    expires = serializers.CharField(read_only=True)


class PosDeviceLinkRequestSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField()
    posid = serializers.IntegerField()
    xpubkey = serializers.CharField()

    def validate(self, data):
        wallet_hash = data["wallet_hash"]
        posid = data["posid"]

        pos_device = PosDevice.objects.filter(wallet_hash=wallet_hash, posid = posid).first()
        if not pos_device:
            raise serializers.ValidationError("pos device does not exist")
        if pos_device.linked_device:
            raise serializers.ValidationError("pos device is already linked")

        return data

    def save_link_request(self):
        code_ttl = 60 * 5 # seconds
        code = uuid4().hex
        redis_key = f"posdevicelink:{code}"
        data = json.dumps(self.validated_data).encode()
        REDIS_CLIENT.set(redis_key, data, ex=code_ttl)
        now = timezone.now()
        expires = now + timezone.timedelta(seconds=code_ttl)
        return { "code": code, "expires": expires.timestamp() }


class LinkedDeviceInfoSerializer(serializers.ModelSerializer):
    link_code = serializers.CharField()

    class Meta:
        model = LinkedDeviceInfo
        fields = [
            "link_code",
            "device_id",
            "name",
            "device_model",
            "os",
            "is_suspended",
        ]

        extra_kwargs = {
            "is_suspended": {
                "read_only": True,
            },
        }

    def remove_link_code_data(self):
        if not self.instance:
            return
        redis_key = f"posdevicelink:{self.instance.link_code}"
        encoded_data = REDIS_CLIENT.delete(redis_key)

    def validate(self, data):
        link_code = data["link_code"]
        redis_key = f"posdevicelink:{link_code}"
        encoded_data = REDIS_CLIENT.get(redis_key)
        try:
            link_code_data = json.loads(encoded_data)
            data_serializer = PosDeviceLinkRequestSerializer(data=link_code_data)
            if not data_serializer.is_valid():
                raise serializers.ValidationError("data from link code is invalid")
        except (json.JSONDecodeError, TypeError):
            raise serializers.ValidationError("link code invalid")

        data["link_code_data"] = data_serializer.validated_data

        wallet_hash = data["link_code_data"]["wallet_hash"]
        posid = data["link_code_data"]["posid"]

        pos_device = PosDevice.objects.filter(wallet_hash=wallet_hash, posid=posid).first()
        if not pos_device:
            raise serializers.ValidationError("pos device not found")

        if pos_device.linked_device and pos_device.linked_device != link_code:
            raise serializers.ValidationError("pos device is already linked")

        return data

    @transaction.atomic
    def create(self, validated_data):
        link_code = validated_data["link_code"]
        link_code_data = validated_data.pop("link_code_data")

        wallet_hash = link_code_data["wallet_hash"]
        posid = link_code_data["posid"]
        xpubkey = link_code_data["xpubkey"]

        pos_device = PosDevice.objects.filter(wallet_hash=wallet_hash, posid=posid).first()
        if not pos_device:
            raise ValidationError("pos device not found")

        if pos_device.linked_device and pos_device.linked_device.link_code == link_code:
            instance = super().update(pos_device.linked_device, validated_data)
        else:
            instance = super().create(validated_data)
            pos_device.linked_device = instance
            pos_device.save()

        pos_device.xpubkey = xpubkey
        return instance


class PosDeviceSerializer(serializers.ModelSerializer):
    posid = serializers.IntegerField(help_text="Resolves to a new posid if negative value")
    wallet_hash = serializers.CharField()
    name = serializers.CharField(required=False)
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    linked_device = LinkedDeviceInfoSerializer(read_only=True)

    class Meta:
        model = PosDevice
        fields = [
            "posid",
            "wallet_hash",
            "name",
            "branch_id",
            "linked_device",
        ]

    def __init__(self, *args, supress_merchant_info_validations=False, xpubkey=None, **kwargs):
        self.supress_merchant_info_validations = supress_merchant_info_validations
        if xpubkey:
            self.fields["xpubkey"] = serializers.CharField(read_only=True)
        return super().__init__(*args, **kwargs)
    
    def get_unique_together_validators(self):
        """Overriding method to disable unique together checks"""
        return []

    def validate_posid(self, value):
        if self.instance and self.instance.posid != value:
            raise serializers.ValidationError("editing posid is not allowed")
        return value

    def validate_wallet_hash(self, value):
        if self.instance and self.instance.wallet_hash != value:
            raise serializers.ValidationError("editing posid is not allowed")

        if not self.supress_merchant_info_validations:
            if not Merchant.objects.filter(wallet_hash = value).exists():
                raise serializers.ValidationError("Wallet hash does not have merchant information", code="missing_merchant_info")

        return value

    def validate_branch_id(self, value):
        if not value:
            return value

        try:
            Branch.objects.get(id=value)
        except Branch.DoesNotExist:
            raise serializers.ValidationError("branch not found")
        return value

    def validate(self, data):
        wallet_hash = data["wallet_hash"]
        branch_id = data.get("branch_id", None)
        if branch_id:
            try:
                Branch.objects.get(merchant__wallet_hash=wallet_hash, id=branch_id)
            except Branch.DoesNotExist:
                raise serializers.ValidationError("branch_id under merchant wallet_hash not found")
        return data

    def create(self, validated_data, *args, **kwargs):
        wallet_hash = validated_data["wallet_hash"]
        posid = validated_data["posid"]

        if posid < 0:
            posid = PosDevice.find_new_posid(wallet_hash)
            if posid is None:
                raise serializers.ValidationError("unable to find new posid")
            validated_data["posid"] = posid

        try:
            instance = PosDevice.objects.get(posid=posid, wallet_hash=wallet_hash)
            instance = super().update(instance, validated_data)
            send_device_update(instance, action="update")
            return instance
        except PosDevice.DoesNotExist:
            pass

        instance = super().create(validated_data, *args, **kwargs)
        send_device_update(instance, action="create")
        return instance


class POSPaymentSerializer(serializers.Serializer):
    transaction = serializers.CharField()
    otp = serializers.CharField(required=False)
    payment_timestamp = TimestampField()
    pos_device = PosDeviceSerializer(supress_merchant_info_validations=True)

    def save(self):
        validated_data = self.validated_data
        otp = validated_data.get("otp", None)
        payment_timestamp = validated_data.get("payment_timestamp", timezone.now())
        pos_device_data = validated_data["pos_device"]
        wallet_hash = pos_device_data["wallet_hash"]
        posid = pos_device_data["posid"]

        response = {
            "success": False,
            "txid": "",
        }

        otp_timestamp = round(payment_timestamp.timestamp())
        response["otp_timestamp"] = otp_timestamp
        if otp is not None:
            if otp != generate_pos_device_totp(wallet_hash, posid, timestamp=otp_timestamp):
                raise serializers.ValidationError("Provided OTP does not match")
            response["otp_valid"] = True
        else:
            response["otp"] = generate_pos_device_totp(wallet_hash, posid, timestamp=otp_timestamp)

        broadcast_response = broadcast_transaction(validated_data["transaction"])
        if not broadcast_response["success"]:
            error_msg = "Failed to broadcast transaction"
            if "error" in broadcast_response and broadcast_response["error"]:
                error_msg = broadcast_response["error"]
            raise serializers.ValidationError(error_msg)

        response["success"] = True
        response["txid"] = broadcast_response["txid"]

        return response


class POSPaymentResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    txid = serializers.CharField()
    otp = serializers.CharField(required=False)
    otp_timestamp = serializers.IntegerField()
    otp_valid = serializers.CharField(required=False)


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = [
            "landmark",
            "location",
            "street",
            "city",
            "country",
            "longitude",
            "latitude",
        ]


class MerchantSerializer(serializers.ModelSerializer):
    location = LocationSerializer(required=False)
    wallet_hash = serializers.CharField() # to supress unique validation

    class Meta:
        model = Merchant
        fields = [
            "id",
            "wallet_hash",
            "name",
            "primary_contact_number",
            "location",
        ]


    @transaction.atomic()
    def create(self, validated_data):
        wallet_hash = validated_data["wallet_hash"]
        existing_merchant = Merchant.objects.filter(wallet_hash=wallet_hash).first()
        if existing_merchant:
            return self.update(existing_merchant, validated_data)

        location_data = validated_data.pop("location", None)
        if location_data:
            location_serializer = LocationSerializer(data=location_data)
            if not location_serializer.is_valid():
                raise serializers.ValidationError({ "location": location_serializer.errors })
            validated_data["location"] = location_serializer.save()

        return super().create(validated_data)

    @transaction.atomic()
    def update(self, instance, validated_data):
        location_data = validated_data.pop("location", None)

        if location_data:
            location_serializer = LocationSerializer(instance.location, data=location_data, partial=self.partial)
            if not location_serializer.is_valid():
                raise serializers.ValidationError({ "location": location_serializer.errors })
            validated_data["location"] = location_serializer.save()

        return super().update(instance, validated_data)


class BranchMerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = [
            "id",
            "wallet_hash",
            "name",
        ]


class BranchSerializer(serializers.ModelSerializer):
    merchant_wallet_hash = serializers.CharField(write_only=True)
    merchant = BranchMerchantSerializer(read_only=True)
    location = LocationSerializer(required=False)

    class Meta:
        model = Branch
        fields = [
            "id",
            "merchant_wallet_hash",
            "merchant",
            "name",
            "location",
        ]

    def validate_merchant_wallet_hash(self, value):
        if self.instance and self.instance.merchant.wallet_hash != value:
            raise serializers.ValidationError("merchant wallet hash is not editable")

        try:
            Merchant.objects.get(wallet_hash=value)
        except Merchant.DoesNotExist:
            raise serializers.ValidationError("merchant not found")
        return value


    @transaction.atomic()
    def create(self, validated_data):
        merchant_wallet_hash = validated_data.pop("merchant_wallet_hash")
        try:
            validated_data["merchant"] = Merchant.objects.get(wallet_hash=merchant_wallet_hash)
        except Merchant.DoesNotExist:
            raise serializers.ValidationError("merchant not found")

        location_data = validated_data.pop("location", None)
        if location_data:
            location_serializer = LocationSerializer(data=location_data)
            if not location_serializer.is_valid():
                raise serializers.ValidationError({ "location": location_serializer.errors })
            validated_data["location"] = location_serializer.save()

        return super().create(validated_data)

    @transaction.atomic()
    def update(self, instance, validated_data):
        location_data = validated_data.pop("location", None)

        if location_data:
            location_serializer = LocationSerializer(instance.location, data=location_data, partial=self.partial)
            if not location_serializer.is_valid():
                raise serializers.ValidationError({ "location": location_serializer.errors })
            validated_data["location"] = location_serializer.save()

        return super().update(instance, validated_data)
