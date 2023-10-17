from django.db import models
from .currency import FiatCurrency

from django.utils.crypto import get_random_string
from cryptography.fernet import Fernet
from django.conf import settings
import random

import logging
logger = logging.getLogger(__name__)

class Peer(models.Model):
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