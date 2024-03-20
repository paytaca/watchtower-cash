from django.core.exceptions import ValidationError
from django.db import models
from .peer import Peer
from django.apps import apps

class IdentifierFormat(models.Model):
  format = models.CharField(max_length=64, unique=True)

  def __str__(self):
    return self.format

class PaymentType(models.Model):
  name = models.CharField(max_length=100, db_index=True)
  formats = models.ManyToManyField(IdentifierFormat)
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
  identifier_format = models.ForeignKey(IdentifierFormat, on_delete=models.PROTECT, null=True)
  created_at = models.DateTimeField(auto_now_add=True, editable=False)
  modified_at = models.DateTimeField(auto_now=True)

  def __str__(self):
    return f"{self.id} | {self.payment_type} | {self.owner.name}"
  
  def delete(self, *args, **kwargs):
    # disable deleting of payment method if it is used by any Ad
    Ad = apps.get_model('rampp2p', 'Ad')
    ads_using_this = Ad.objects.filter(deleted_at__isnull=True, payment_methods__id=self.id)
    if ads_using_this.exists():
      raise ValidationError("Cannot delete Payment Method while it is used by an Ad")
    super().delete(*args, **kwargs)