from rest_framework import serializers
from rampp2p.models import Arbiter

class ArbiterSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    wallet_hash = serializers.CharField(required=False, write_only=True)
    name = serializers.CharField(required=False)
    chat_identity_id = serializers.CharField(required=False)
    public_key = serializers.CharField(required=False)
    address = serializers.CharField(required=False)
    address_path = serializers.CharField(required=False)
    is_disabled = serializers.BooleanField(read_only=True)

    class Meta:
        model = Arbiter
        fields = [
            'id',
            'wallet_hash',
            'name',
            'chat_identity_id',
            'public_key',
            'address',
            'address_path',
            'is_disabled'
        ]