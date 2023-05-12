from rest_framework import serializers
from rampp2p.models import (
    Contract, 
    Order
)

class ContractSerializer(serializers.ModelSerializer):
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
    class Meta:
        model = Contract
        fields = [
            'id',
            'txid',
            'order',
            'contract_address',
            'created_at'
        ]