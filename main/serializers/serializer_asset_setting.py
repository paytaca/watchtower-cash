from rest_framework import serializers
from main.models import AssetSetting

class AssetSettingSerializer (serializers.ModelSerializer):
    class Meta:
        model = AssetSetting
        fields = [
            "wallet_hash",
            "custom_list",
            "unlisted_list",
            "favorites"
        ]
