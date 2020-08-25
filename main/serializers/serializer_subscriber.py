from main.models import Subscriber
from rest_framework import serializers, exceptions

class Subscriber(serializers.ModelSerializer):
    model = Subscriber
    fields = [
            'user',
            'subscription',
            'confirmed',
            'date_started',
        ]