from django.db import models
from django.utils.translation import gettext_lazy as _

from .order import Order

class StatusType(models.TextChoices):
  SUBMITTED = 'SBM', _('Submitted')
  CONFIRMED = 'CNF', _('Confirmed')
  PAID      = 'PD', _('Paid')
  APPEALED  = 'APL', _('Appealed')
  RELEASED  = 'RLS', _('Released')
  REFUNDED  = 'RFN', _('Refunded')
  CANCELED  = 'CNCL', _('Canceled')

class Status(models.Model):
  status = models.CharField(max_length=5, choices=StatusType.choices, editable=False)
  order = models.ForeignKey(Order, on_delete=models.CASCADE, editable=False)
  created_at = models.DateTimeField(auto_now_add=True, editable=False)