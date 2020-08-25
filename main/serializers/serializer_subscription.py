from main.models import Subscription
from rest_framework import serializers, exceptions

class Subscription(serializers.ModelSerializer):
    model = Subscription
    fields = [
        'token',
        'address',
        'slp',
        'bch'
    ]