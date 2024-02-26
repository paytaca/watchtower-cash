from rest_framework import serializers

from main.models import AssetPriceLog


class AssetPriceLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetPriceLog
        fields = [
            "id",
            "currency",
            "relative_currency",
            "timestamp",
            "source",
            "price_value",
        ]
