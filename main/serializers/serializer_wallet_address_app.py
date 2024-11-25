from requests import Response
from rest_framework import serializers

from main.models import WalletAddressApp

class WalletAddressAppSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletAddressApp
        fields = '__all__'
