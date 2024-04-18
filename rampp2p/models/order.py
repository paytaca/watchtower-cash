from django.db import models
from .ad import AdSnapshot
from .peer import Peer
from .arbiter import Arbiter
from .payment import PaymentMethod

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
