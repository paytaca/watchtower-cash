from rest_framework import serializers

from .models import (
    Memo
)

class MemoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Memo
        fields = [
            "id",
            "wallet_hash",
            "created_at",
            "note",
            "txid"

        ]