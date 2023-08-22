from rest_framework import serializers

from purelypeer.models import Vault, CashdropNftPair


class VaultSerializer(serializers.ModelSerializer):    
    class Meta:
        model = Vault
        fields = '__all__'


class CreateCashdropNftPairSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashdropNftPair
        fields = '__all__'
