from django.db import models
from .peer import Peer

class PaymentTypeFormat(models.Model):
  format = models.CharField(max_length=64, db_index=True)

  def __str__(self):
    return self.format

class PaymentType(models.Model):
  name = models.CharField(max_length=100, db_index=True)
  format = models.ManyToManyField(PaymentTypeFormat)
  is_disabled = models.BooleanField(default=False)
  created_at = models.DateTimeField(auto_now_add=True)
  modified_at = models.DateTimeField(auto_now=True)

  def __str__(self):
    return self.name

class PaymentMethod(models.Model):
  payment_type = models.ForeignKey(PaymentType, on_delete=models.PROTECT)
  owner = models.ForeignKey(Peer, on_delete=models.CASCADE)
  account_name = models.CharField(max_length=100, blank=True, null=True, default='')
  account_identifier = models.CharField(max_length=100)
  created_at = models.DateTimeField(auto_now_add=True, editable=False)
  modified_at = models.DateTimeField(auto_now=True)

  def __str__(self):
    return f"{self.id} | {self.payment_type} | {self.owner.name}"