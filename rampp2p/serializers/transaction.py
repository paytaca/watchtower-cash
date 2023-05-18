from rest_framework import serializers
from rampp2p.models import Contract, Transaction, Recipient

class TransactionSerializer(serializers.ModelSerializer):
  contract = serializers.PrimaryKeyRelatedField(queryset=Contract.objects.all())
  class Meta:
    model = Transaction
    fields = [
      'contract',
      'action',
      'txid',
      'created_at'
    ]

class RecipientSerializer(serializers.ModelSerializer):
  transaction = serializers.PrimaryKeyRelatedField(queryset=Transaction.objects.all())
  class Meta:
    model = Recipient
    fields = [
      'transaction',
      'address',
      'created_at'
    ]