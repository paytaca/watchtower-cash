from django.db import models

from .currency import FiatCurrency

class Peer(models.Model):
  nickname = models.CharField(max_length=100, unique=True)
  wallet_address = models.CharField(max_length=100, blank=True, null=True) # required if is_arbiter=True
  default_fiat = models.ForeignKey(
    FiatCurrency, 
    on_delete=models.SET_NULL, 
    related_name='peers',
    blank=True,
    null=True
  )
  is_arbiter = models.BooleanField(default=False)
  is_disabled = models.BooleanField(default=False)
  created_at = models.DateTimeField(auto_now_add=True)
  modified_at = models.DateTimeField(auto_now=True)