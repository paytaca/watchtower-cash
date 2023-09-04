from rest_framework import serializers

from purelypeer.models import Vault, Voucher


class VaultSerializer(serializers.ModelSerializer):    
    class Meta:
        model = Vault
        fields = '__all__'


class CreateVoucherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Voucher
        fields = '__all__'
