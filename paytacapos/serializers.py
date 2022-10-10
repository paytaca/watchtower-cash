from rest_framework import serializers

from .utils.broadcast import broadcast_transaction
from .utils.totp import generate_pos_device_totp


class PosDeviceSerializer(serializers.Serializer):
    posid = serializers.IntegerField()
    wallet_hash = serializers.CharField()


class POSPaymentSerializer(serializers.Serializer):
    transaction = serializers.CharField()
    otp = serializers.CharField(required=False)
    pos_device = PosDeviceSerializer()

    def save(self):
        validated_data = self.validated_data
        otp = validated_data.get("otp", None)
        pos_device_data = validated_data["pos_device"]
        wallet_hash = pos_device_data["wallet_hash"]
        posid = pos_device_data["posid"]

        response = {
            "success": False,
            "txid": "",
        }

        if otp is not None:
            if otp != generate_pos_device_totp(wallet_hash, posid):
                raise serializers.ValidationError("Provided OTP does not match")
            response["otp_valid"] = True
        else:
            response["otp"] = generate_pos_device_totp(wallet_hash, posid)

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
    otp_valid = serializers.CharField(required=False)
