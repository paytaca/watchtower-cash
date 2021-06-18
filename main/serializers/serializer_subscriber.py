from rest_framework import serializers, exceptions

class SubscriberSerializer(serializers.Serializer):
    address = serializers.CharField(max_length=200)
    webhook_url = serializers.CharField(max_length=200, required=False, allow_blank=True)
    wallet_hash = serializers.CharField(max_length=200, required=False, allow_blank=True)
    wallet_index = serializers.IntegerField(required=False, allow_null=True)
