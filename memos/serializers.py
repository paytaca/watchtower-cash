from rest_framework import serializers

from .models import (
    Memo
)

class RampShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shift
        fields = [
            "id",
            "wallet_hash",
            "created_at",
            "note",
            "txid"

        ]