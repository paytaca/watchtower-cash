from django.db import models

class PaymentType(models.Model):
  name = models.CharField(max_length=100)
  is_disabled = models.BooleanField(default=False)
  created_at = models.DateTimeField(auto_now_add=True)
  modified_at = models.DateTimeField(auto_now=True)

class PaymentMethod(models.Model):
  payment_type = models.ForeignKey('PaymentType', on_delete=models.PROTECT)
  owner = models.ForeignKey('Peer', on_delete=models.CASCADE)
  account_name = models.CharField(max_length=100)
  account_number = models.CharField(max_length=100)
  created_at = models.DateTimeField(auto_now_add=True)
  modified_at = models.DateTimeField(auto_now=True)