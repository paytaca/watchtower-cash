from django.db import models
from django.apps import apps
from django.utils.crypto import get_random_string

class Peer(models.Model):
    chat_identity_id = models.IntegerField(null=True, blank=True)
    name = models.CharField(max_length=64, unique=True)
    wallet_hash = models.CharField(max_length=75, unique=True, db_index=True)
    public_key = models.CharField(max_length=75)
    address = models.CharField(max_length=75)
    address_path = models.CharField(max_length=10, null=True)
    
    is_disabled = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    is_online = models.BooleanField(default=False)
    last_online_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.name

    def average_rating(self):
        Feedback = apps.get_model('rampp2p', 'Feedback')
        avg_rating = Feedback.objects.filter(to_peer=self).aggregate(models.Avg('rating'))['rating__avg']
        return avg_rating

class ReservedName(models.Model):
    peer = models.ForeignKey(Peer, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=64, unique=True)
    key = models.CharField(max_length=100, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.redeemed_at and not self.created_at:
            self.key = get_random_string(24)
        super().save(*args, **kwargs)
