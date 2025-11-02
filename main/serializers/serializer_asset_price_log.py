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


class UnifiedAssetPriceSerializer(serializers.Serializer):
    """
    Serializer for unified asset prices (BCH and tokens)
    """
    id = serializers.IntegerField(required=False, allow_null=True, help_text="AssetPriceLog ID")
    asset = serializers.CharField(help_text="Asset identifier: 'BCH' for Bitcoin Cash or 'ct/<category_id>' for CashTokens")
    asset_type = serializers.CharField(help_text="'bch' or 'cashtoken'")
    asset_name = serializers.CharField(required=False, allow_null=True, help_text="Token name if available")
    asset_symbol = serializers.CharField(required=False, allow_null=True, help_text="Token symbol if available")
    currency = serializers.CharField(help_text="Currency code (USD, PHP, BCH, etc.)")
    price_value = serializers.DecimalField(max_digits=25, decimal_places=8, help_text="Price value")
    timestamp = serializers.DateTimeField(help_text="Price timestamp")
    source = serializers.CharField(help_text="Price source (coingecko, cauldron, calculated, etc.)")
    source_ids = serializers.DictField(required=False, allow_null=True, help_text="Source IDs used for calculation (for calculated prices)")
    calculation = serializers.CharField(required=False, allow_null=True, help_text="Calculation method if price is calculated")
