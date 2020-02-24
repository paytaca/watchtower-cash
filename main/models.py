from django.db import models
from django.utils import timezone


class Token(models.Model):
    tokenid = models.CharField(max_length=200)
    confirmation_limit = models.IntegerField(default=0)

    def __str__(self):
        return self.tokenid


class BlockHeight(models.Model):
    number = models.IntegerField(default=0, unique=True)
    transactions_count = models.IntegerField(default=0)
    created_datetime = models.DateTimeField(null=True, blank=True)
    updated_datetime = models.DateTimeField(null=True, blank=True)
    processed = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.id:
            self.created_datetime = timezone.now()
        if self.processed:
            self.updated_datetime = timezone.now()
        super(BlockHeight,self).save(*args, **kwargs)


class Transaction(models.Model):
    txid = models.CharField(max_length=200, unique=True)
    amount = models.FloatField(default=0)
    saved_by_client = models.BooleanField(default=False)
    blockheight = models.ForeignKey(BlockHeight, on_delete=models.CASCADE, related_name='transactions', null=True)
    source = models.CharField(max_length=200, null=True)
    created_datetime = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.txid


class SlpAddress(models.Model):
    token = models.ForeignKey(Token, on_delete=models.CASCADE, related_name='slpaddress')
    address = models.CharField(max_length=200)
    transactions = models.ManyToManyField(Transaction) 

    class Meta:
        verbose_name = 'Slp Address'
        verbose_name_plural = 'Slp Addresses'
        
    def __str__(self):
        return self.address