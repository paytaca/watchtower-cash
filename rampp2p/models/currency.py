from django.db import models

class FiatCurrency(models.Model):
  name = models.CharField(max_length=100)
  abbrev = models.CharField(max_length=3, unique=True)
  created_at = models.DateTimeField(auto_now_add=True)

class CryptoCurrency(models.Model):
  name = models.CharField(max_length=100)
  abbrev = models.CharField(max_length=10, unique=True)
  created_at = models.DateTimeField(auto_now_add=True)