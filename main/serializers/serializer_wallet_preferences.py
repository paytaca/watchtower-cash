from rest_framework import serializers

from main.models import WalletPreferences

class WalletPreferencesSerializer(serializers.ModelSerializer):
    wallet_hash = serializers.CharField(source="wallet__wallet_hash", read_only=True)

    class Meta:
        model = WalletPreferences
        fields = [
            "wallet_hash",
            "selected_currency",
        ]
