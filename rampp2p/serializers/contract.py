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
    arbiter = serializers.SerializerMethodField()
    seller = serializers.SerializerMethodField()
    buyer = serializers.SerializerMethodField()
    servicer = serializers.SerializerMethodField()
    timestamp = serializers.SerializerMethodField()
    class Meta:
        model = Contract
        fields = ContractSerializer.Meta.fields + [
            'arbiter',
            'seller',
            'buyer',
            'servicer',
            'timestamp'
        ]
    
    def get_arbiter(self, instance: Contract):
        arbiter, _, _ = self.get_parties(instance)
        return {
            'public_key': arbiter.public_key,
            'address': arbiter.address
        }
    
    def get_seller(self, instance: Contract):
        _, seller, _ = self.get_parties(instance)
        return {
            'public_key': seller.public_key,
            'address': seller.address
        }

    def get_buyer(self, instance: Contract):
        _, _, buyer = self.get_parties(instance)
        return {
            'public_key': buyer.public_key,
            'address': buyer.address
        }

    def get_servicer(self, _):
        return {
            'public_key': settings.SERVICER_PK,
            'address': settings.SERVICER_ADDR
        }
    
    def get_timestamp(self, instance: Contract):
        return instance.created_at.timestamp()

    def get_parties(self, instance: Contract):
        arbiter = instance.order.arbiter
        seller = None
        buyer = None
        ad = instance.order.ad_snapshot
        order = instance.order
        if ad.trade_type == TradeType.SELL:
            seller = ad.owner
            buyer = order.owner
        else:
            seller = order.owner
            buyer = ad.owner
        return arbiter, seller, buyer