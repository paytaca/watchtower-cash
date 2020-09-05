from main.models import Subscription
from rest_framework import serializers, exceptions

class SubscriptionSerializer(serializers.Serializer):
    user = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    sendto = serializers.CharField(required=True)
    slp = serializers.CharField()
    bch = serializers.CharField()

    
    