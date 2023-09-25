from rest_framework import serializers
from rampp2p.models import Contract, Transaction, Recipient

class TransactionSerializer(serializers.ModelSerializer):
  contract = serializers.PrimaryKeyRelatedField(queryset=Contract.objects.all())
  class Meta:
    model = Transaction
    fields = [
      'id',
      'contract',
      'action',
      'txid',
      'valid',
      'verifying',
      'created_at'
    ]
    depth = 1

class RecipientSerializer(serializers.ModelSerializer):
  transaction = serializers.PrimaryKeyRelatedField(queryset=Transaction.objects.all())
  value = serializers.DecimalField(decimal_places=8, max_digits=18)
  class Meta:
    model = Recipient
    fields = [
      'transaction',
      'address',
      'value',
      'created_at'
    ]