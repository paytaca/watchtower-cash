from django.db import models
from django.utils.translation import gettext_lazy as _
import json
from .peer import Peer
from .order import Order

class AppealType(models.TextChoices):
    RELEASE = 'RLS', _('Release')
    REFUND  = 'RFN', _('Refund')

class Appeal(models.Model):
    type = models.CharField(
        max_length=10, 
        choices=AppealType.choices,
        null=False
    )
    reasons = models.TextField(
        blank=True,
        null=True
    )
    owner = models.ForeignKey(
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
    resolved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.id)

    def set_reasons(self, reasons):
        self.reasons = json.dumps(reasons)
    
    def get_reasons(self):
        return json.loads(self.reasons) if self.reasons else []
