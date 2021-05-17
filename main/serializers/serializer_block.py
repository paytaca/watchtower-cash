from main.models import Block
from rest_framework import serializers, exceptions

class BlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = Block
        fields = [
            'number',
            'transactions_count',
            'created_datetime',
            'updated_datetime',
            'processed',
            'currentcount'
        ]