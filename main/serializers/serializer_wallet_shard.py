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
