from rest_framework import serializers
from drf_yasg.utils import swagger_serializer_method


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


class AssetPriceChartSerializer(serializers.ModelSerializer):
    timestamp = serializers.SerializerMethodField()
    class Meta:
        model = AssetPriceLog
        fields = [
            "timestamp",
            "price_value",
        ]

    @swagger_serializer_method(serializer_or_field=serializers.IntegerField)
    def get_timestamp(self, obj):
        timestamp = None
        if isinstance(obj, AssetPriceLog):
            timestamp = obj.timestamp
        elif isinstance(obj, dict):
            timestamp = obj.get("timestamp")

        return int(timestamp.timestamp() * 1000)
