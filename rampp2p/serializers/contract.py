from rest_framework import serializers
from django.conf import settings
from rampp2p.models import (
    Contract, 
    Order,
    TradeType
)

class ContractSerializer(serializers.ModelSerializer):
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
    class Meta:
        model = Contract
        fields = [
            'id',
            'order',
            'address',
            'created_at'
        ]
        depth = 1

class ContractDetailSerializer(ContractSerializer):
    pubkeys = serializers.SerializerMethodField()
    addresses = serializers.SerializerMethodField()
    timestamp = serializers.SerializerMethodField()
    class Meta:
        model = Contract
        fields = ContractSerializer.Meta.fields + [
            'pubkeys',
            'addresses',
            'timestamp'
        ]
    
    def get_pubkeys(self, contract):
        arbiter, seller, buyer = self.get_parties(contract)
        servicer = self.get_servicer()
        return {
            'arbiter': arbiter.public_key,
            'seller': seller.public_key,
            'buyer': buyer.public_key,
            'servicer': servicer.get('public_key')
        }
    
    def get_addresses(self, contract):
        arbiter, seller, buyer = self.get_parties(contract)
        servicer = self.get_servicer()
        return {
            'arbiter': arbiter.address,
            'seller': seller.address,
            'buyer': buyer.address,
            'servicer': servicer.get('address')
        }

    def get_servicer(self):
        return {
            'public_key': settings.SERVICER_PK,
            'address': settings.SERVICER_ADDR
        }
    
    def get_timestamp(self, contract):
        return contract.created_at.timestamp()

    def get_parties(self, contract):
        arbiter = contract.order.arbiter
        seller = None
        buyer = None
        ad_snapshot = contract.order.ad_snapshot
        order = contract.order
        if ad_snapshot.trade_type == TradeType.SELL:
            seller = ad_snapshot.ad.owner
            buyer = order.owner
        else:
            seller = order.owner
            buyer = ad_snapshot.ad.owner
        return arbiter, seller, buyer