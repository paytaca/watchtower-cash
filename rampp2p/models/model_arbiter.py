from django.db import models
from django.apps import apps
from .model_currency import FiatCurrency

class Arbiter(models.Model):
    chat_identity_id = models.IntegerField(null=True, blank=True)
    name = models.CharField(max_length=100)
    wallet_hash = models.CharField(max_length=75, unique=True, db_index=True)
    public_key = models.CharField(max_length=75)
    address = models.CharField(max_length=75)
    address_path = models.CharField(max_length=10, null=True)
    fiat_currencies = models.ManyToManyField(FiatCurrency, blank=True)
    is_disabled = models.BooleanField(default=True)
    inactive_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    modified_at = models.DateTimeField(auto_now=True)
    is_online = models.BooleanField(default=False)
    last_online_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.name
    
    def average_rating(self):
        ArbiterFeedback = apps.get_model('rampp2p', 'ArbiterFeedback')
        avg_rating = ArbiterFeedback.objects.filter(to_arbiter=self).aggregate(models.Avg('rating'))['rating__avg']
        return "{:.1f}".format(avg_rating) if avg_rating is not None else None
