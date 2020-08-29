from main.models import Transaction
from rest_framework import serializers, exceptions

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            'txid',
            'address',
            'amount',
            'acknowledge',
            'blockheight',
            'token'
        ]