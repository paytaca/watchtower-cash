import pytz
from datetime import datetime
from django.utils import timezone
from rest_framework import serializers

from .models import PosDevice
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

    class Meta:
        model = PosDevice
        fields = [
            "posid",
            "wallet_hash",
            "name",
        ]
    
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
        return value

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
    pos_device = PosDeviceSerializer()

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
