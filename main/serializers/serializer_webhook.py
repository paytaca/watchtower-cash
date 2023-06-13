from rest_framework import serializers


class BcmrWebhookSerializer(serializers.Serializer):
    category = serializers.CharField(max_length=255)
    is_nft = serializers.BooleanField(default=False)
    index = serializers.IntegerField(default=0)
    txid = serializers.CharField(max_length=100)
    commitment = serializers.CharField(max_length=255, allow_blank=True, allow_null=True)
    capability = serializers.CharField(max_length=50, allow_blank=True, allow_null=True)
