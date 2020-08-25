from main.models import Transaction
from rest_framework import serializers, exceptions

class TransactionSerializer(serializers.ModelSerializer):
    model = Transaction
    fields = [
        'txid',
        'address',
        'amount',
        'acknowledge',
        'blockheight',
        'source',
        'created_datetime',
        'token',
        'scanning',
        'subscribed',
        'spentIndex',
    ]