from requests import Response
from rest_framework import serializers

from main.models import WalletShard

class WalletShardSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletShard
        fields = [
            "shard",
            "first_identifier",
            "second_identifier"
        ]

    def update(self, instance, validated_data):
        instance.shard = validated_data.get('shard', instance.shard)
        instance.first_identifier = validated_data.get('first_identifier', instance.first_identifier)
        instance.second_identifier = validated_data.get('second_identifier', instance.second_identifier)
        instance.save()
        return instance