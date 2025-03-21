from rest_framework import serializers

class SubscriberSerializer(serializers.Serializer):
    address = serializers.CharField(
        max_length=200,
        required=False
    )
    addresses = serializers.DictField(
        child=serializers.CharField(max_length=200),
        required=False
    )
    project_id = serializers.CharField(max_length=200, required=False, allow_blank=True)
    wallet_hash = serializers.CharField(max_length=200, required=False, allow_blank=True)
    wallet_index = serializers.IntegerField(required=False, allow_null=True)
    address_index = serializers.IntegerField(required=False, allow_null=True)
    webhook_url = serializers.CharField(max_length=200, required=False, allow_blank=True)