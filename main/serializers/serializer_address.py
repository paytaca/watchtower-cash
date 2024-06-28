from rest_framework import serializers

class AddressInfoSerializer(serializers.Serializer):
    address = serializers.CharField(required=False)
    token_address = serializers.CharField(required=False)
    wallet_hash = serializers.CharField(required=False)
    project_id = serializers.CharField(required=False)
    has_subscribed_push_notifications = serializers.BooleanField(required=False)
