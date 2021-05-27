from rest_framework import serializers, exceptions

class SubscriberSerializer(serializers.Serializer):
    address = serializers.CharField(max_length=200)
    web_url = serializers.CharField(max_length=200, required=False, allow_blank=True)
    telegram_id = serializers.CharField(max_length=200, required=False, allow_blank=True)
