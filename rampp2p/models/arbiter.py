from django.db import models
from django.apps import apps

class Arbiter(models.Model):
    name = models.CharField(max_length=100)
    public_key = models.CharField(max_length=100)
    address = models.CharField(max_length=100)
    wallet_hash = models.CharField(
        max_length=100,
        unique=True
    )
    is_disabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    
    def average_rating(self):
        ArbiterFeedback = apps.get_model('rampp2p', 'ArbiterFeedback')
        return ArbiterFeedback.objects.filter(to_arbiter=self).aggregate(models.Avg('rating'))['rating__avg']