from django.db import models
from .order import Order

class Contract(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, unique=True)
    address = models.CharField(max_length=100, blank=True, null=True)
    version = models.CharField(max_length=100, default='')
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    def __str__(self):
        return f'{self.id} | {self.address}'

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
        return f'{self.id} | {self.member_type} | {self.address}'