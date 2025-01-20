from rest_framework import serializers
from django.conf import settings
import rampp2p.models as models

class ContractMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ContractMember
        fields = [
            'id',
            'member_ref_id',
            'member_type',
            'pubkey',
            'address',
            'address_path'
        ]

class ContractSerializer(serializers.ModelSerializer):
    order = serializers.PrimaryKeyRelatedField(queryset=models.Order.objects.all())
    class Meta:
        model = models.Contract
        fields = [
            'id',
            'order',
            'address',
            'created_at'
        ]

class ContractDetailSerializer(ContractSerializer): 
    members = ContractMemberSerializer(many=True, read_only=True)
    pubkeys = serializers.SerializerMethodField()
    addresses = serializers.SerializerMethodField()
    timestamp = serializers.SerializerMethodField()
    class Meta:
        model = models.Contract
        fields = ContractSerializer.Meta.fields + [
            'members',
            'pubkeys',
            'addresses',
            'timestamp'
        ]

    def get_pubkeys(self, contract):
        arbiter, seller, buyer = self.get_parties(contract)
        servicer = self.get_servicer()
        return {
            'arbiter': arbiter.pubkey,
            'seller': seller.pubkey,
            'buyer': buyer.pubkey,
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
        members = models.ContractMember.objects.filter(contract__id=contract.id)
        arbiter, seller, buyer = None, None, None
        for member in members:
            type = member.member_type
            if (type == models.ContractMember.MemberType.ARBITER):
                arbiter = member
            if (type == models.ContractMember.MemberType.SELLER):
                seller = member
            if (type == models.ContractMember.MemberType.BUYER):
                buyer = member

        return arbiter, seller, buyer