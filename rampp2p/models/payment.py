from django.db import models
from .peer import Peer

class PaymentType(models.Model):
  name = models.CharField(max_length=100, db_index=True)
  format = models.CharField(max_length=100)
  is_disabled = models.BooleanField(default=False)
  created_at = models.DateTimeField(auto_now_add=True)
  modified_at = models.DateTimeField(auto_now=True)

  def __str__(self):
    return self.name

class PaymentMethod(models.Model):
  payment_type = models.ForeignKey(PaymentType, on_delete=models.PROTECT, editable=False)
  owner = models.ForeignKey(Peer, on_delete=models.CASCADE, editable=False)
  account_name = models.CharField(max_length=100)
  account_identifier = models.CharField(max_length=100)
  created_at = models.DateTimeField(auto_now_add=True, editable=False)
  modified_at = models.DateTimeField(auto_now=True)

  def __str__(self):
    return f"id: {self.id} | owner: {self.owner.name}"