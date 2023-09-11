from rest_framework import serializers
from rampp2p.models import Arbiter

class ArbiterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Arbiter
        fields = [
            'id',
            'name',
            'public_key',
            'address',
            'is_disabled'
        ]