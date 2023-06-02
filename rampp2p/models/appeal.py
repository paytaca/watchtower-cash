from django.db import models
from django.utils.translation import gettext_lazy as _

from .peer import Peer
from .order import Order

class AppealType(models.TextChoices):
    # CANCEL = 'CNCL', _('Cancel')
    RELEASE = 'RLS', _('Release')
    REFUND  = 'RFN', _('Refund')

class Appeal(models.Model):
    type = models.CharField(
        max_length=10, 
        choices=AppealType.choices, 
        editable=False
    )
    creator = models.ForeignKey(
        Peer, 
        on_delete=models.PROTECT, 
        related_name='created_appeals', 
        editable=False
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='order_appeals',
        editable=False
    )
    is_approved = models.BooleanField(default=False)
    is_approved_at = models.DateTimeField(blank=True, null=True)
    is_closed = models.BooleanField(default=False)
    is_closed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now=True)

