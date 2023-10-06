from django.db import models
from .currency import FiatCurrency

from django.utils.crypto import get_random_string
import random

class Peer(models.Model):
    nickname = models.CharField(max_length=100)
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

    # Temporary fields to test authentication
    auth_token = models.CharField(max_length=40, unique=True, null=True)
    auth_nonce = models.CharField(max_length=6, null=True)

    def __str__(self):
        return self.wallet_hash

    def create_auth_token(self):
        self.auth_token = get_random_string(40)
        self.save()

    def update_auth_nonce(self):
        self.auth_nonce = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        self.save()