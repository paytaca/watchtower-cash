import pytz
from datetime import datetime
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import (
    PosDevice,
    Location,
    Merchant,
    Branch,
)
from .utils.broadcast import broadcast_transaction
from .utils.totp import generate_pos_device_totp


class TimestampField(serializers.IntegerField):
    def to_representation(self, value):
        return datetime.timestamp(value)

    def to_internal_value(self, data):
        return datetime.fromtimestamp(data).replace(tzinfo=pytz.UTC)


class PosDeviceSerializer(serializers.ModelSerializer):
    posid = serializers.IntegerField(help_text="Resolves to a new posid if negative value")
    wallet_hash = serializers.CharField()
    name = serializers.CharField(required=False)
    branch_id = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = PosDevice
        fields = [
            "posid",
            "wallet_hash",
            "name",
            "branch_id",
        ]

    def __init__(self, *args, supress_merchant_info_validations=False, **kwargs):
        self.supress_merchant_info_validations = supress_merchant_info_validations
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
        try:
            Branch.objects.get(id=value)
        except Branch.DoesNotExist:
            raise serializers.ValidationError("branch not found")

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
            return super().update(instance, validated_data)
        except PosDevice.DoesNotExist:
            pass

        return super().create(validated_data, *args, **kwargs)


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
