import uuid

from django.db import models


class RegistrationChallenge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account_type = models.CharField(max_length=7, choices=[('peer', 'Peer'), ('arbiter', 'Arbiter')])
    payload_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)


class RegistrationRequestBucket(models.Model):
    # Hash the scope, identity and time window; do not retain raw IP addresses.
    id = models.CharField(primary_key=True, max_length=64)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
