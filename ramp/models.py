from django.db import models
from django.contrib.postgres.fields import JSONField

# Create your models here.
class Shift(models.Model):
    wallet_hash = models.CharField(max_length=100)
    bch_address = models.CharField(max_length=100)
    ramp_type =  models.CharField(max_length=20)
    shift_id = models.CharField(max_length=50, unique=True)
    quote_id = models.CharField(max_length=50, unique=True)
    date_shift_created = models.DateTimeField(null=True, blank=True)
    date_shift_completed = models.DateTimeField(null=True, blank=True)
    shift_info = JSONField(default=dict)
    shift_status = models.CharField(max_length=50, default="waiting")
