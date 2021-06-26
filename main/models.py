from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField
from django.conf import settings
import uuid


class Token(models.Model):
    name = models.CharField(max_length=50, blank=True)
    tokenid = models.CharField(
        max_length=200,
        blank=True,
        unique=True,
        db_index=True
    )
    confirmation_limit = models.IntegerField(default=0)
    decimals = models.IntegerField(default=0)

    token_ticker = models.CharField(max_length=50)
    token_type = models.IntegerField(default=1)
    nft_token_group = models.ForeignKey(
        "main.Token",
        on_delete=models.CASCADE,
        related_name='children',
        null=True
    )

    class Meta:
        unique_together = ('name', 'tokenid',)

    def __str__(self):
        if self.tokenid:
            return f"{self.name} | {self.tokenid[0:7]}"
        else:
            return str(self.name)


class BlockHeight(models.Model):
    number = models.IntegerField(default=0, unique=True, db_index=True)
    transactions_count = models.IntegerField(default=0)
    created_datetime = models.DateTimeField(null=True, blank=True)
    updated_datetime = models.DateTimeField(null=True, blank=True)
    processed = models.BooleanField(default=False)
    currentcount = models.IntegerField(default=0)
    problematic = JSONField(default=list, blank=True)
    unparsed = JSONField(default=list, blank=True)
    requires_full_scan = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.id:
            self.created_datetime = timezone.now()
        if self.processed:
            self.updated_datetime = timezone.now()
        if self.number < settings.START_BLOCK:
            self.requires_full_scan = False
        super(BlockHeight,self).save(*args, **kwargs)
    
    def __str__(self):
        return str(self.number)


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, blank=True)
    date_created = models.DateTimeField(default=timezone.now)

    def __str__(self):
        if self.name:
            return self.name
        else:
            return str(self.id)


class Wallet(models.Model):
    wallet_hash = models.CharField(
        max_length=70,
        db_index=True
    )
    wallet_type = models.CharField(
        max_length=5,
        db_index=True
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='wallets',
        null=True,
        blank=True
    )
    date_created = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.wallet_hash


class Address(models.Model):
    address = models.CharField(max_length=70, unique=True, db_index=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='addresses',
        null=True,
        blank=True
    )
    wallet = models.ForeignKey(
        Wallet,
        related_name='addresses',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    wallet_index = models.IntegerField(
        null=True,
        blank=True
    )
    date_created = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name_plural = 'Addresses'

    def __str__(self):
        return self.address

    def save(self, *args, **kwargs):
        wallet = self.wallet
        if wallet and not wallet.wallet_type:
            if self.address.startswith('simpleledger:'):
                wallet.wallet_type = 'slp'
            elif self.address.startswith('bitcoincash:'):
                wallet.wallet_type = 'bch'
            wallet.save()
        super(Address, self).save(*args, **kwargs)


class Transaction(models.Model):
    txid = models.CharField(max_length=70, db_index=True)
    address = models.ForeignKey(
        Address,
        related_name='transactions',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    amount = models.FloatField(default=0, db_index=True)
    acknowledged = models.BooleanField(null=True, default=None)
    blockheight = models.ForeignKey(
        BlockHeight,
        on_delete=models.CASCADE,
        related_name='transactions',
        null=True,
        blank=True
    )
    source = models.CharField(max_length=50, db_index=True)
    created_datetime = models.DateTimeField(default=timezone.now)
    token = models.ForeignKey(
        Token,
        on_delete=models.CASCADE
    )
    index = models.IntegerField(default=0, db_index=True)
    spent = models.BooleanField(default=False)
    spending_txid = models.CharField(max_length=70, blank=True, db_index=True)
    spend_block_height = models.ForeignKey(
        BlockHeight,
        related_name='spent_transactions',
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING
    )
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.SET_NULL,
        related_name='transactions',
        null=True,
        blank=True
    )

    class Meta:
        unique_together = [
            'txid',
            'address',
            'index'
        ]

    def __str__(self):
        return self.txid


class Recipient(models.Model):
    web_url = models.CharField(max_length=300, blank=True)
    telegram_id = models.CharField(max_length=50, blank=True)
    valid = models.BooleanField(default=True)

    def __str__(self):
        if self.web_url:
            return self.web_url
        elif self.telegram_id:
            return self.telegram_id
        else:
            return 'N/A'


class Subscription(models.Model):
    address = models.ForeignKey(
        Address,
        on_delete=models.CASCADE,
        related_name='subscriptions',
        db_index=True,
        null=True
    )
    recipient = models.ForeignKey(
        Recipient,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subscriptions'
    )
    websocket=models.BooleanField(default=False)


class WalletHistory(models.Model):
    INCOMING = 'incoming'
    OUTGOING = 'outgoing'
    RECORD_TYPE_OPTIONS = [
        (INCOMING, 'Incoming'),
        (OUTGOING, 'Outgoing')
    ]

    txid = models.CharField(
        max_length=70,
        unique=True,
        db_index=True
    )
    record_type = models.CharField(
        max_length=10,
        blank=True,
        choices=RECORD_TYPE_OPTIONS
    )
    amount = models.FloatField(default=0)
    token = models.ForeignKey(
        Token,
        related_name='wallet_records',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    date_created = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.txid
