from rest_framework import serializers
from rampp2p.models import Receipt, Order

class ReceiptSerializer(serializers.ModelSerializer):
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
    class Meta:
        model = Receipt
        fields = [
            'txid', 
            'order'
        ]
        read_only_fields = ['order']