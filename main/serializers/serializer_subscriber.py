from main.models import Subscriber
from rest_framework import serializers, exceptions

class SubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscriber
        fields = [
                'user',
                'subscription',
                'confirmed',
                'date_started',
            ]