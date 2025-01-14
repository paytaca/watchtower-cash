from django.db import models
from django.utils import timezone

from django.utils.crypto import get_random_string
from cryptography.fernet import Fernet
from django.conf import settings
import random

import logging
logger = logging.getLogger(__name__)

class AuthToken(models.Model):
    wallet_hash = models.CharField(max_length=100)
    nonce = models.CharField(max_length=6, null=True, blank=True)
    key = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    nonce_expires_at = models.DateTimeField(null=True, blank=True)
    key_expires_at = models.DateTimeField(null=True)

    def is_nonce_expired(self):
        return timezone.now() > self.nonce_expires_at
    
    def is_key_expired(self):
        return timezone.now() > self.key_expires_at

    def update_key(self):
        key = get_random_string(40)
        cipher_suite = Fernet(settings.FERNET_KEY)
        self.key = cipher_suite.encrypt(key.encode()).decode()
        self.key_expires_at = timezone.now() + timezone.timedelta(days=3) # Token expires in 3 days
        self.save()
    
    def update_nonce(self):
        self.nonce = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        self.nonce_expires_at = timezone.now() + timezone.timedelta(minutes=1) # Token expires in 1 minute
        self.save()
    
    def __str__(self):
        return str(self.id)