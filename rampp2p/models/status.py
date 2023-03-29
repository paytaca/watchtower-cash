from django.db import models
from django.utils.translation import gettext_lazy as _

class Status(models.Model):

  class StatusType(models.TextChoices):
    SUBMITTED = 'SBM', _('Submitted')
    CONFIRMED = 'CNF', _('Confirmed')
    PAID      = 'PD', _('Paid')
    APPEALED  = 'APL', _('Appealed')
    RELEASED  = 'RLS', _('Released')
    REFUNDED  = 'RFN', _('Refunded')

  status = models.CharField(max_length=3, choices=StatusType.choices, editable=False)
  order = models.ForeignKey('Order', on_delete=models.CASCADE, editable=False)
  created_at = models.DateTimeField(auto_now_add=True, editable=False)

  # TODO: should not be deletable