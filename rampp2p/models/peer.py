from django.db import models

class Peer(models.Model):
  nickname = models.CharField(max_length=100, unique=True)
  default_fiat = models.ForeignKey(
    'FiatCurrency', 
    on_delete=models.SET_NULL, 
    related_name='peers', 
    null=True
  )
  created_at = models.DateTimeField(auto_now_add=True)
  modified_at = models.DateTimeField(auto_now=True)