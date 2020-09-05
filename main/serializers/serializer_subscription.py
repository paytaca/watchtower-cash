from main.models import Subscription
from rest_framework import serializers, exceptions

class SubscriptionSerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True)
    token_address = serializers.CharField(required=True)
    destination_address = serializers.CharField(required=True)
    tokenid = serializers.CharField(allow_blank=True)
    tokenname = serializers.CharField()

    
    