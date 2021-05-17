from main.models import Address
from rest_framework import serializers, exceptions

class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ['address',]