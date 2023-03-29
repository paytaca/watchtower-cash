from django.db import models

class Arbiter(models.Model):
  name = models.CharField(max_length=100)
  wallet_address = models.CharField(max_length=50)
  is_disabled = models.BooleanField(default=False)
  created_at = models.DateTimeField(auto_now_add=True, editable=False)
  modified_at = models.DateTimeField(auto_now=True)