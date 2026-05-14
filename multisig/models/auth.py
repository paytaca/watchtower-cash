import logging
from django.db import models

LOGGER = logging.getLogger(__name__)

class ServerIdentity(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True)
    public_key = models.CharField(max_length=66, unique=True)
    message = models.CharField(max_length=255, null=True, blank=True)
    signature = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True, default=None)
    updated_at = models.DateTimeField(auto_now=True)
    # type = coordinator = has public_key, signature, message
    # type viewer = has public_key
