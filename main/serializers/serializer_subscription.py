from main.models import Subscription
from rest_framework import serializers, exceptions

class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = [
            'token',
            'address',
            'slp',
            'bch'
        ]