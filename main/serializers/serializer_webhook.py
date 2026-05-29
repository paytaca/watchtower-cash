from rest_framework import serializers


class BcmrWebhookSerializer(serializers.Serializer):
    category = serializers.CharField(max_length=255)
    is_nft = serializers.BooleanField(default=False)
    index = serializers.IntegerField(default=0)
    txid = serializers.CharField(max_length=100)
    commitment = serializers.CharField(max_length=255, allow_blank=True, allow_null=True)
    capability = serializers.CharField(max_length=50, allow_blank=True, allow_null=True)


class RecipientWebhookSecretCreateSerializer(serializers.Serializer):
    web_url = serializers.CharField(max_length=300)
    webhook_secret = serializers.CharField(min_length=32, max_length=64)


class RecipientWebhookSecretRotateSerializer(serializers.Serializer):
    web_url = serializers.CharField(max_length=300)
    current_webhook_secret = serializers.CharField(allow_blank=True)
    new_webhook_secret = serializers.CharField(min_length=32, max_length=64, allow_blank=True)
