from rest_framework import serializers


class BcmrWebhookSerializer(serializers.Serializer):
    category = serializers.CharField(max_length=255)
    name = serializers.CharField(max_length=255, allow_blank=True)
    description = serializers.CharField(max_length=255, allow_blank=True)
    symbol = serializers.CharField(max_length=100, allow_blank=True)
    decimals = serializers.IntegerField(default=0)
    image_url = serializers.CharField(max_length=255, allow_blank=True)
