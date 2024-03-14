from django.db import models
from .currency import FiatCurrency
from django.apps import apps

import logging
logger = logging.getLogger(__name__)

class Peer(models.Model):
    chat_identity_id = models.IntegerField(null=True, blank=True)
    name = models.CharField(max_length=100, unique=True)
    wallet_hash = models.CharField(max_length=75, unique=True, db_index=True)
    public_key = models.CharField(max_length=75)
    address = models.CharField(max_length=75)
    address_path = models.CharField(max_length=10, null=True)
    is_disabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def average_rating(self):
        Feedback = apps.get_model('rampp2p', 'Feedback')
        avg_rating = Feedback.objects.filter(to_peer=self).aggregate(models.Avg('rating'))['rating__avg']
        return avg_rating