from rest_framework import serializers

from .models import (
    Shift
)

class RampShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shift
        fields = [
            "id",
            "wallet_hash",
            "bch_address",
            "ramp_type",
            "shift_id",
            "quote_id",
            "date_shift_created",
            "date_shift_completed",
            "shift_info",
            "shift_status"

        ]

    # def create(self, validated_data):
    #     return Shift.objects.create(**validated_data)

