from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField


class Token(models.Model):
    name = models.CharField(max_length=100, null=True)
    tokenid = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        unique=True,
        db_index=True
    )
    confirmation_limit = models.IntegerField(default=0)
    decimals = models.IntegerField(default=0)

    class Meta:
        unique_together = ('name', 'tokenid',)

    def __str__(self):
        if self.tokenid:
            return f"{self.name} | {self.tokenid[0:7]}"
        else:
            return str(self.name)
    
    def save(self, *args, **kwargs):

        if not self.id and self.name != 'bch':
            mod = __import__('main.utils', fromlist=['slptoken'])
            obj = mod.slptoken.SLPToken(self.tokenid)
            self.decimals = obj.get_decimals()
            self.name = obj.get_name()
        super(Token, self).save(*args, **kwargs)

class BlockHeight(models.Model):
    number = models.IntegerField(default=0, unique=True, db_index=True)
    transactions_count = models.IntegerField(default=0)
    created_datetime = models.DateTimeField(null=True, blank=True)
    updated_datetime = models.DateTimeField(null=True, blank=True)
    processed = models.BooleanField(default=False)
    currentcount = models.IntegerField(default=0)
    problematic = JSONField(default=list, blank=True)
    unparsed = JSONField(default=list, blank=True)


    def save(self, *args, **kwargs):
        if not self.id:
            self.created_datetime = timezone.now()
        if self.processed:
            self.updated_datetime = timezone.now()
        super(BlockHeight,self).save(*args, **kwargs)

    def __str__(self):
        return str(self.number)

class Transaction(models.Model):
    txid = models.CharField(max_length=200, db_index=True)
    address = models.CharField(max_length=500,null=True, db_index=True)
    amount = models.FloatField(default=0, db_index=True)
    acknowledged = models.BooleanField(default=False)
    blockheight = models.ForeignKey(
        BlockHeight,
        on_delete=models.CASCADE,
        related_name='transactions',
        null=True
    )
    source = models.CharField(max_length=200, null=True, db_index=True)
    created_datetime = models.DateTimeField(default=timezone.now)
    token = models.ForeignKey(
        Token,
        on_delete=models.CASCADE
    )
    index = models.IntegerField(default=0, db_index=True)
    spent = models.BooleanField(default=False)
    spend_block_height = models.ForeignKey(
        BlockHeight,
        related_name='spent_transactions',
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING
    )

    def __str__(self):
        return self.txid

class Recipient(models.Model):
    web_url = models.CharField(max_length=500,null=True, blank=True)
    telegram_id = models.CharField(max_length=100,null=True, blank=True)
    valid = models.BooleanField(default=True)

    def __str__(self):
        if self.web_url:
            return self.web_url
        elif self.telegram_id:
            return self.telegram_id
        else:
            return 'N/A'

class SlpAddress(models.Model):
    address = models.CharField(max_length=200, unique=True, db_index=True)
    transactions = models.ManyToManyField(
        Transaction,
        related_name='slpaddress',
        blank=True
    )

    class Meta:
        verbose_name = 'SLP Address'
        verbose_name_plural = 'SLP Addresses'
        
    def __str__(self):
        return self.address

class BchAddress(models.Model):
    address = models.CharField(max_length=200, unique=True, db_index=True)
    transactions = models.ManyToManyField(
        Transaction,
        related_name='bchaddress',
        blank=True
    )
    scanned = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = 'BCH Address'
        verbose_name_plural = 'BCH Addresses'
        
    def __str__(self):
        return self.address

class Subscription(models.Model):
    recipient = models.ForeignKey(
        Recipient,
        on_delete=models.CASCADE,
        null=True,
        related_name='subscriptions'
    )
    slp = models.ForeignKey(
        SlpAddress,
        on_delete=models.DO_NOTHING,
        related_name='subscriptions',
        null=True
    )
    bch = models.ForeignKey(
        BchAddress,
        on_delete=models.DO_NOTHING,
        related_name='subscriptions',
        null=True
    )