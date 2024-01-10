from django.db import models
from .currency import FiatCurrency
from django.apps import apps

import logging
logger = logging.getLogger(__name__)

class Peer(models.Model):
    chat_identity_id = models.CharField(max_length=100, null=True)
    name = models.CharField(max_length=100)
    public_key = models.CharField(max_length=100)
    address = models.CharField(max_length=100)
    wallet_hash = models.CharField(
        max_length=100,
        unique=True
    )
    default_fiat = models.ForeignKey(
        FiatCurrency, 
        on_delete=models.SET_NULL, 
        related_name='peers',
        blank=True,
        null=True
    )
    is_disabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def average_rating(self):
        Feedback = apps.get_model('rampp2p', 'Feedback')
        avg_rating = Feedback.objects.filter(to_peer=self).aggregate(models.Avg('rating'))['rating__avg']
        return avg_rating