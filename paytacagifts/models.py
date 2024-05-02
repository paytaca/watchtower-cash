from django.db import models
from uuid import uuid4

class Wallet(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    date_created = models.DateTimeField(auto_now_add=True)
    wallet_hash = models.CharField(max_length=64, db_index=True)

    def __str__(self):
        return str(self.wallet_hash)
    
    class Meta:
        ordering = [
            '-date_created'
        ]

class Campaign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    date_created = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=50)
    limit_per_wallet = models.FloatField()
    wallet = models.ForeignKey(Wallet, related_name="campaigns", on_delete=models.CASCADE)

    def __str__(self):
        return str(self.id)
    
    class Meta:
        ordering = [
            '-date_created'
        ]

class Gift(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    date_created = models.DateTimeField(auto_now_add=True)
    gift_code_hash = models.CharField(max_length=70, unique=True)
    address = models.CharField(max_length=64, db_index=True)
    amount = models.FloatField(default=0)
    share = models.CharField(max_length=255)
    date_funded = models.DateTimeField(blank=True, null=True) 
    date_claimed = models.DateTimeField(blank=True, null=True)
    claim_txid = models.CharField(max_length=70, blank=True, db_index=True)
    wallet = models.ForeignKey(Wallet, related_name="gifts", on_delete=models.CASCADE)
    campaign = models.ForeignKey(Campaign, related_name="gifts", on_delete=models.CASCADE, blank=True, null=True)

    def __str__(self):
        return str(self.id)
    
    class Meta:
        ordering = [
            '-date_created',
            '-date_funded'
        ]
        indexes = [
            models.Index(fields=['gift_code_hash']),
            models.Index(fields=['date_funded']),
            models.Index(fields=['date_claimed']),
        ]


class Claim(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    date_created = models.DateTimeField(auto_now_add=True)
    amount = models.FloatField(default=0)
    wallet = models.ForeignKey(Wallet, related_name="claims", on_delete=models.CASCADE)
    gift = models.ForeignKey(Gift, related_name="claims", on_delete=models.CASCADE)
    campaign = models.ForeignKey(Campaign, related_name="claims", on_delete=models.CASCADE, null=True)
    succeeded = models.BooleanField(default=False)

    class Meta:
        ordering = [
            '-date_created'
        ]
        unique_together = ('wallet', 'gift')

    def __str__(self):
        return str(self.id)
