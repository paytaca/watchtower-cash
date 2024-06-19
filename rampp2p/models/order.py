from django.db import models
from .ad import AdSnapshot
from .peer import Peer
from .arbiter import Arbiter
from .payment import PaymentMethod, PaymentType

class Order(models.Model):
    ad_snapshot = models.ForeignKey(AdSnapshot, on_delete=models.PROTECT, editable=False)
    owner = models.ForeignKey(Peer, on_delete=models.PROTECT, editable=False, related_name="created_orders")
    chat_session_ref = models.CharField(max_length=100, null=True, blank=True)
    arbiter = models.ForeignKey(Arbiter, on_delete=models.PROTECT, blank=True, null=True, related_name="arbitrated_orders")
    locked_price = models.DecimalField(max_digits=18, decimal_places=8, default=0, editable=False)
    crypto_amount = models.DecimalField(max_digits=18, decimal_places=8, default=0, editable=False)
    payment_methods = models.ManyToManyField(PaymentMethod)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    appealable_at = models.DateTimeField(null=True)
    expires_at = models.DateTimeField(null=True)

    def __str__(self):
        return f'{self.id}'

class OrderPaymentMethod(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.SET_NULL, null=True)
    payment_type = models.ForeignKey(PaymentType, on_delete=models.PROTECT)
    
class OrderMember(models.Model):
    class MemberType(models.TextChoices):
        SELLER = 'SELLER'
        BUYER = 'BUYER'
        ARBITER = 'ARBITER'

    type = models.CharField(max_length=10, choices=MemberType.choices, null=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='members')
    peer = models.ForeignKey(Peer, on_delete=models.CASCADE, related_name='order_members', null=True, blank=True)
    arbiter = models.ForeignKey(Arbiter, on_delete=models.CASCADE, related_name='order_members', null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        member_name = ''
        if self.peer:
            member_name = self.peer.name
        elif self.arbiter:
            member_name = self.arbiter.name
        return f'{self.id} | Order #{self.order.id} | {self.type} | {member_name}'

    class Meta:
         constraints = [
            models.UniqueConstraint(
                fields=['type', 'peer', 'order'],
                condition=models.Q(peer__isnull=False),
                name='unique_peer_order'
            ),
            models.UniqueConstraint(
                fields=['type', 'arbiter', 'order'],
                condition=models.Q(arbiter__isnull=False),
                name='unique_arbiter_order'
            ),
        ]