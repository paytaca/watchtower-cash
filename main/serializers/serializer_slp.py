from main.models import SlpAddress
from rest_framework import serializers, exceptions

class SlpAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = SlpAddress
        fields = ['address',]