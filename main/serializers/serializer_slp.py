from main.models import SlpAddress
from rest_framework import serializers, exceptions

class SlpAddress(serializers.ModelSerializer):
    class Meta:
        model = SlpAddress
        fields = ['address',]