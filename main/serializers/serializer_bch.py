from main.models import BchAddress
from rest_framework import serializers, exceptions

class BchAddress(serializers.ModelSerializer):
    class Meta:
        model = BchAddress
        fields = ['address',]