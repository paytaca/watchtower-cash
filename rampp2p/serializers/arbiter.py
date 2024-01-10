from rest_framework import serializers
from rampp2p.models import Arbiter

class ArbiterProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Arbiter
        fields = [
            'id',
            'chat_identity_id',
            'name',
            'public_key',
            'address',
            'is_disabled'
        ]

class ArbiterWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Arbiter
        fields = [
            'name',
            'chat_identity_id',
            'wallet_hash',
            'public_key',
            'address'
        ]

class ArbiterReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Arbiter
        fields = [
            'id',
            'chat_identity_id',
            'name',
            'public_key',
            'address',
            'is_disabled'
        ]