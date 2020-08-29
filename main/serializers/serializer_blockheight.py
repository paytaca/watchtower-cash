from main.models import BlockHeight
from rest_framework import serializers, exceptions

class BlockHeightSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlockHeight
        fields = [
            'number',
            'transactions_count',
            'created_datetime',
            'updated_datetime',
            'processed',
            'currentcount'
        ]