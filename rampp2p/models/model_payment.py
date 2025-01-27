from django.db import models
from .model_peer import Peer

class PaymentType(models.Model):
  full_name = models.CharField(max_length=100, db_index=True)
  short_name = models.CharField(max_length=50, default='')
  notes = models.CharField(max_length=200, null=True, blank=True)
  is_disabled = models.BooleanField(default=False)
  created_at = models.DateTimeField(auto_now_add=True)
  modified_at = models.DateTimeField(auto_now=True)

  def __str__(self):
    if self.short_name:
      return self.short_name
    return self.full_name

class PaymentMethod(models.Model):
  payment_type = models.ForeignKey(PaymentType, on_delete=models.PROTECT)
  owner = models.ForeignKey(Peer, on_delete=models.CASCADE)
  created_at = models.DateTimeField(auto_now_add=True, editable=False)

  def __str__(self):
    return f"{self.id}"
  
class DynamicPaymentTypeField(models.Model):
  class ModelRef(models.TextChoices):
    ORDER = 'order'
  
  class FieldRef(models.TextChoices):
    ID = 'id'
    TRACKING_ID = 'tracking_id'
  
  fieldname = models.CharField(max_length=100)
  model_ref = models.CharField(max_length=5, choices=ModelRef.choices, db_index=True)
  field_ref = models.CharField(max_length=50, choices=FieldRef.choices, db_index=True)
  payment_type = models.ForeignKey(PaymentType, on_delete=models.CASCADE, related_name='dynamic_fields')

  def __str__(self):
    return f'{self.id}'

class PaymentTypeField(models.Model):
  fieldname = models.CharField(max_length=100)
  format = models.CharField(max_length=100, blank=True, null=True)
  description = models.CharField(max_length=100, blank=True, null=True)
  payment_type = models.ForeignKey(PaymentType, on_delete=models.CASCADE, related_name='fields')
  required = models.BooleanField(default=True)

  def __str__(self):
    return f"{self.id}"

class PaymentMethodField(models.Model):
  payment_method = models.ForeignKey(PaymentMethod, on_delete=models.CASCADE, related_name='values')
  field_reference = models.ForeignKey(PaymentTypeField, on_delete=models.PROTECT, related_name='values')
  value = models.CharField(max_length=100)
  created_at = models.DateTimeField(auto_now_add=True, editable=False)
  modified_at = models.DateTimeField(auto_now=True)

  def __str__(self):
    return f"{self.id}"
