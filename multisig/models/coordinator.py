import logging
from django.db import models

LOGGER = logging.getLogger(__name__)

class ServerIdentity(models.Model):
    name = models.CharField(max_length=255)
    public_key = models.CharField(max_length=66, unique=True)
    message = models.CharField(max_length=255)
    signature = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True, default=None)
    updated_at = models.DateTimeField(auto_now=True)

class KeyRecord(models.Model):
    publisher = models.ForeignKey(ServerIdentity, related_name='publisher_key_records', on_delete=models.CASCADE)
    published_for = models.ForeignKey(ServerIdentity, related_name='published_for_key_records', on_delete=models.CASCADE)
    key_record = models.TextField()