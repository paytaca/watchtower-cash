from django.core.exceptions import ValidationError
from django.db import models
from .peer import Peer
from django.apps import apps

class IdentifierFormat(models.Model):
  format = models.CharField(max_length=64, unique=True)

  def __str__(self):
    return self.format

class PaymentType(models.Model):
  full_name = models.CharField(max_length=100, db_index=True)
  short_name = models.CharField(max_length=50, default='')
  formats = models.ManyToManyField(IdentifierFormat)
  notes = models.CharField(max_length=200, null=True, blank=True)
  is_disabled = models.BooleanField(default=False)
  has_qr_code = models.BooleanField(default=False)
  acc_name_required = models.BooleanField(default=False)
  created_at = models.DateTimeField(auto_now_add=True)
  modified_at = models.DateTimeField(auto_now=True)

  def __str__(self):
    if self.short_name:
      return self.short_name
    return self.full_name

class PaymentMethod(models.Model):
  payment_type = models.ForeignKey(PaymentType, on_delete=models.PROTECT)
  owner = models.ForeignKey(Peer, on_delete=models.CASCADE)
  account_name = models.CharField(max_length=100, blank=True, null=True, default='')
  account_identifier = models.CharField(max_length=100)
  identifier_format = models.ForeignKey(IdentifierFormat, on_delete=models.PROTECT, null=True)
  created_at = models.DateTimeField(auto_now_add=True, editable=False)
  modified_at = models.DateTimeField(auto_now=True)

  def __str__(self):
    return f"{self.id}"

####### V2 Payments #######
# class PaymentTypeV2(models.Model):
#   full_name = models.CharField(max_length=100, db_index=True)
#   short_name = models.CharField(max_length=50, default='')
#   notes = models.CharField(max_length=200, null=True, blank=True)
#   is_disabled = models.BooleanField(default=False)
#   created_at = models.DateTimeField(auto_now_add=True)

class PaymentTypeField(models.Model):
  fieldname = models.CharField(max_length=100)
  format = models.CharField(max_length=100, blank=True, null=True)
  description = models.CharField(max_length=100, blank=True, null=True)
  payment_type = models.ForeignKey(PaymentType, on_delete=models.CASCADE, related_name='fields')
  required = models.BooleanField(default=True)

  def __str__(self):
    return f"{self.id}"

# class PaymentMethodV2(models.Model):
#   owner = models.ForeignKey(Peer, on_delete=models.CASCADE)
#   payment_type = models.ForeignKey(PaymentType, on_delete=models.PROTECT)
#   created_at = models.DateTimeField(auto_now_add=True, editable=False)

class PaymentMethodField(models.Model):
  payment_method = models.ForeignKey(PaymentMethod, on_delete=models.CASCADE, related_name='values')
  field_reference = models.ForeignKey(PaymentTypeField, on_delete=models.PROTECT, related_name='values')
  value = models.CharField(max_length=100)
  created_at = models.DateTimeField(auto_now_add=True, editable=False)
  modified_at = models.DateTimeField(auto_now=True)

  def __str__(self):
    return f"{self.id}"