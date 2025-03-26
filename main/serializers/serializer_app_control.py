from rest_framework import serializers
from main.models import AppControl

class AppControlSerializer (serializers.ModelSerializer):
    class Meta:
        model = AppControl
        fields = [
            "feature_name",
            "is_enabled",
            "enabled_countries"
        ]
