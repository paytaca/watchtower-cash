from django.db import models
from django.utils.translation import gettext_lazy as _
from .order import Order

class StatusType(models.TextChoices):
  SUBMITTED         = 'SBM', _('Submitted')
  ESCROW_PENDING    =  'ESCRW_PN', _('Escrow Pending')
  ESCROWED          = 'ESCRW', _('Escrowed')
  PAID_PENDING      = 'PD_PN', _('Paid Pending')
  PAID              = 'PD', _('Paid')
  RELEASE_APPEALED  = 'RLS_APL', _('Appealed for Release')
  REFUND_APPEALED   = 'RFN_APL', _('Appealed for Refund')
  RELEASE_PENDING   = 'RLS_PN', _('Release Pending')
  RELEASED          = 'RLS', _('Released')
  REFUND_PENDING    = 'RFN_PN', _('Refund Pending')
  REFUNDED          = 'RFN', _('Refunded')
  CANCELED          = 'CNCL', _('Canceled')

class Status(models.Model):
  status = models.CharField(max_length=10, choices=StatusType.choices, editable=False, blank=False)
  order = models.ForeignKey(Order, on_delete=models.CASCADE, editable=False)
  created_at = models.DateTimeField(auto_now_add=True, editable=False)