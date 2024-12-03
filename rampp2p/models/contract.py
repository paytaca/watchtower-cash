from django.db import models
from .order import Order

import logging
logger = logging.getLogger(__name__)

class Contract(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, unique=True)
    address = models.CharField(max_length=100, blank=True, null=True)
    version = models.CharField(max_length=100, null=True)
    service_fee = models.IntegerField(null=True, editable=False)
    arbitration_fee = models.IntegerField(null=True, editable=False)
    contract_fee = models.IntegerField(null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    def __str__(self):
        return f'{self.id}'
    
    def get_total_fees(self):
        total = None
        try:
            total = self.service_fee + self.arbitration_fee + self.contract_fee
        except Exception as err:
            logger.exception(err.args[0])
        return total
    
    def get_fees(self):
        return {
            'service_fee': self.service_fee,
            'arbitration_fee': self.arbitration_fee,
            'contract_fee': self.contract_fee
        }
    
    def get_members(self):
        members = ContractMember.objects.filter(contract__id=self.id)
        arbiter, seller, buyer = None, None, None
        for member in members:
            type = member.member_type
            if (type == ContractMember.MemberType.ARBITER):
                arbiter = member
            if (type == ContractMember.MemberType.SELLER):
                seller = member
            if (type == ContractMember.MemberType.BUYER):
                buyer = member
        
        return {
            'arbiter': arbiter, 
            'seller': seller, 
            'buyer': buyer
        }

class ContractMember(models.Model):
    class MemberType(models.TextChoices):
        SELLER = 'SELLER'
        BUYER = 'BUYER'
        ARBITER = 'ARBITER'

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='members')
    member_ref_id = models.IntegerField()
    member_type = models.CharField(max_length=10, choices=MemberType.choices)
    pubkey = models.CharField(max_length=75)
    address = models.CharField(max_length=75)
    address_path = models.CharField(max_length=10, null=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        unique_together = ('contract', 'member_type')

    def __str__(self):
        return f'{self.address}'