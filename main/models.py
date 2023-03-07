from django.contrib.contenttypes.fields import GenericRelation, GenericForeignKey
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField
from psqlextra.models import PostgresModel
from psqlextra.query import PostgresQuerySet
from django.contrib.postgres.fields import ArrayField
from django.conf import settings

from main.utils.address_validator import *

import re
import uuid
import web3


class Token(PostgresModel):
    class Capability(models.TextChoices):
        MUTABLE = 'mutable'
        MINTING = 'minting'
        NONE = 'none'  # immutable

    name = models.CharField(max_length=200, blank=True)
    tokenid = models.CharField(
        max_length=70,
        blank=True,
        unique=True,
        db_index=True
    )
    confirmation_limit = models.IntegerField(default=0)
    decimals = models.IntegerField(null=True)

    token_ticker = models.CharField(max_length=200)
    token_type = models.IntegerField(null=True)
    nft_token_group = models.ForeignKey(
        'main.Token',
        on_delete=models.CASCADE,
        related_name='children',
        null=True,
        blank=True
    )
    nft_token_group_details = JSONField(default=dict)
    original_image_url = models.URLField(blank=True)
    medium_image_url = models.URLField(blank=True)
    thumbnail_image_url = models.URLField(blank=True)
    date_created = models.DateTimeField(default=timezone.now)
    date_updated = models.DateTimeField(null=True, blank=True)

    mint_amount = models.BigIntegerField(null=True)

    # cashtoken (FT & NFT only) fields
    is_cashtoken = models.BooleanField(default=False)
    commitment = models.CharField(max_length=255, null=True, blank=True)
    capability = models.CharField(
        max_length=30,
        choices=Capability.choices,
        null=True,
        blank=True
    )

    class Meta:
        unique_together = ('name', 'tokenid',)

    def __str__(self):
        if self.tokenid:
            return f"{self.name} | {self.tokenid[0:7]}"
        else:
            return str(self.name)

    @property
    def is_nft(self):
        if self.token_type == 65:
            return True
        elif self.token_type == 1 and self.decimals == 0 and self.mint_amount == 1:
            return True
        return False

    def save_minting_baton_info(self, minting_baton, save=True):
        self.nft_token_group_details = self.nft_token_group_details or dict()
        self.nft_token_group_details["minting_baton"] = minting_baton
        if save:
            self.save()

    @property
    def info_id(self):
        if self.is_cashtoken:
            ct_prefix = 'ct/'
            return ct_prefix + self.tokenid
        else:
            if self.token_type:
                return 'slp/' + self.tokenid
            else:
                return self.name.lower()
            
    @property
    def image_url(self):
        if self.thumbnail_image_url:
            return self.thumbnail_image_url

        return self.original_image_url

    def get_info(self):
        return {
            'id': self.info_id,
            'name': self.name,
            'symbol': self.token_ticker,
            'is_cashtoken': self.is_cashtoken,
            'decimals': self.decimals,
            'token_type': self.token_type,
            'image_url': self.image_url
        }


class BlockHeight(PostgresModel):
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


class Project(PostgresModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, blank=True)
    date_created = models.DateTimeField(default=timezone.now)

    def __str__(self):
        if self.name:
            return self.name
        else:
            return str(self.id)

    @property
    def wallets_count(self):
        return self.wallets.count()

    @property
    def addresses_count(self):
        return self.addresses.count()

    @property
    def transactions_count(self):
        return WalletHistory.objects.filter(wallet__project_id=self.id).count() 


class Wallet(PostgresModel):
    wallet_hash = models.CharField(
        max_length=70,
        unique=True,
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
    version = models.IntegerField()
    date_created = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.wallet_hash

class Address(PostgresModel):
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
    # `wallet_index` is kept for backward-compatibility with v1 wallets
    wallet_index = models.IntegerField(
        null=True,
        blank=True
    )
    address_path = models.CharField(max_length=10)
    date_created = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Address'
        verbose_name_plural = 'Addresses'

    def __str__(self):
        return self.address

    def save(self, *args, **kwargs):
        wallet = self.wallet
        if wallet and not wallet.wallet_type:
            if is_slp_address(self.address):
                wallet.wallet_type = 'slp'
            elif is_bch_address(self.address):
                wallet.wallet_type = 'bch'
            elif is_token_address(self.address):
                wallet.wallet_type = 'ct'
            elif re.match("0x[0-9a-f]{40}", self.address, re.IGNORECASE):
                wallet.wallet_type = 'sbch'
            elif web3.Web3.isAddress(self.address):
                wallet.wallet_type = 'sbch'
            wallet.save()
        super(Address, self).save(*args, **kwargs)


class Transaction(PostgresModel):
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
    source = models.CharField(max_length=100, db_index=True)
    token = models.ForeignKey(
        Token,
        on_delete=models.CASCADE
    )
    index = models.IntegerField(default=0, db_index=True)
    spent = models.BooleanField(default=False, db_index=True)
    spending_txid = models.CharField(max_length=70, blank=True, db_index=True)
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.SET_NULL,
        related_name='transactions',
        null=True,
        blank=True
    )
    tx_timestamp = models.DateTimeField(null=True, blank=True)
    date_created = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [
            'txid',
            'address',
            'index'
        ]
        ordering = ['-date_created']

    def __str__(self):
        return self.txid


class Recipient(PostgresModel):
    web_url = models.CharField(max_length=300, null=True, blank=True)
    telegram_id = models.CharField(max_length=50, null=True, blank=True)
    valid = models.BooleanField(default=True)

    def __str__(self):
        if self.web_url:
            return self.web_url
        elif self.telegram_id:
            return self.telegram_id
        else:
            return 'N/A'


class Subscription(PostgresModel):
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
    date_created = models.DateTimeField(default=timezone.now)

class WalletHistoryQuerySet(PostgresQuerySet):
    POS_ID_MAX_DIGITS = 4

    def filter_pos(self, wallet_hash, posid=None):
        try:
            posid = int(posid)
            posid = str(posid)
            pad = "0" * (self.POS_ID_MAX_DIGITS-len(posid))
            posid = pad + posid
        except (ValueError, TypeError):
            posid=None
    
        addresses = Address.objects.filter(wallet__wallet_hash=models.OuterRef("wallet__wallet_hash"))
        if posid is None:
            addresses = addresses.annotate(
                address_index = models.functions.Cast(
                    models.functions.Substr(models.F("address_path"), models.Value("0/(\d+)")),
                    models.BigIntegerField(),
                )
            )
            addresses = addresses.filter(
                address_index__gte=10 ** self.POS_ID_MAX_DIGITS,
                address_index__lte=2**31-1,
            )
        else:
            addresses = addresses.filter(address_path__iregex=f"((0|1)/)?0*\d+{posid}")

        addresses = addresses.values("address").distinct()
        addresses_subquery = models.Func(models.Subquery(addresses), function="array")

        return self.filter(
            models.Q(senders__overlap=addresses_subquery) | models.Q(recipients__overlap=addresses_subquery),
            wallet__wallet_hash=wallet_hash,
        )

    def annotate_empty_attributes(self):
        return self.annotate(
            attributes=models.ExpressionWrapper(
                models.Value(None),
                output_field=ArrayField(JSONField()),
            )
        )

    def annotate_attributes(self, *filter_args, **filter_kwargs):
        attrs_qs = TransactionMetaAttribute.objects.filter(
            *filter_args,
            **filter_kwargs,
        ).annotate(
                raw=models.ExpressionWrapper(
                    models.Func(
                        models.Func(
                            models.Value("system_generated"), "system_generated",
                            models.Value("wallet_hash"), "wallet_hash",
                            models.Value("key"), "key",
                            models.Value("value"), "value",
                            function="json_build_object",
                        ),
                        function="array_agg"
                    ),
                    output_field=ArrayField(JSONField()),
                )
            ).values("raw")

        return self.annotate(
            attributes=attrs_qs.filter(txid=models.OuterRef("txid"))
        )

class WalletHistory(PostgresModel):
    objects = WalletHistoryQuerySet.as_manager()

    INCOMING = 'incoming'
    OUTGOING = 'outgoing'
    RECORD_TYPE_OPTIONS = [
        (INCOMING, 'Incoming'),
        (OUTGOING, 'Outgoing')
    ]
    senders = ArrayField(
        ArrayField(models.CharField(max_length=70)),
        default=list,
        blank=True
    )
    recipients = ArrayField(
        ArrayField(models.CharField(max_length=70)),
        default=list,
        blank=True
    )
    wallet = models.ForeignKey(
        Wallet,
        related_name='history',
        on_delete=models.CASCADE,
        null=True
    )
    txid = models.CharField(
        max_length=70,
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
        related_name='wallet_history_records',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    tx_fee = models.FloatField(null=True, blank=True)
    tx_timestamp = models.DateTimeField(null=True,blank=True)
    date_created = models.DateTimeField(default=timezone.now)

    usd_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    market_prices = JSONField(null=True, blank=True)

    class Meta:
        verbose_name = 'Wallet history'
        verbose_name_plural = 'Wallet histories'
        ordering = ['-tx_timestamp', '-date_created']
        unique_together = [
            'wallet',
            'txid'
        ]

    def __str__(self):
        return self.txid

    @property
    def fiat_value(self):
        currency = "USD"
        try:
            if self.wallet and self.wallet.preferences and self.wallet.preferences.selected_currency:
                currency = self.wallet.preferences.selected_currency
        except Wallet.preferences.RelatedObjectDoesNotExist:
            pass

        market_price = None
        if self.market_prices and self.market_prices.get(currency, None):
            market_price = self.market_prices[currency]
        elif not market_price and self.usd_price and currency == "USD":
            market_price = self.usd_price
        
        if not market_price:
            return

        return {
            "currency": currency,
            "value": round(market_price * self.amount, 2),
        }


class WalletNftToken(PostgresModel):
    wallet = models.ForeignKey(
        Wallet,
        related_name='tokens',
        on_delete=models.CASCADE
    )
    token = models.ForeignKey(
        Token,
        related_name='wallets',
        on_delete=models.CASCADE
    )
    date_acquired = models.DateTimeField(default=timezone.now)
    acquisition_transaction = models.ForeignKey(
        Transaction,
        related_name='acquisitions',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    date_dispensed = models.DateTimeField(null=True, blank=True)
    dispensation_transaction = models.ForeignKey(
        Transaction,
        related_name='dispensations',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    class Meta:
       ordering = ['-date_acquired']


class AssetPriceLog(models.Model):
    """
        Price in currency / relative_currency (e.g. USD/BCH)
    """
    currency = models.CharField(max_length=5, db_index=True)
    relative_currency = models.CharField(max_length=5, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    source = models.CharField(max_length=100, null=True, blank=True, db_index=True)

    price_value = models.DecimalField(max_digits=15, decimal_places=3)


class WalletPreferences(PostgresModel):
    wallet = models.OneToOneField(Wallet, on_delete=models.CASCADE, related_name="preferences")
    selected_currency = models.CharField(max_length=5, default="USD")


class TransactionMetaAttribute(PostgresModel):
    txid = models.CharField(max_length=70, db_index=True)

    # to allow wallet scoped attributes
    # used default empty string instead of nullable to trigger a unique_together constraint
    wallet_hash = models.CharField(max_length=70, default="", blank=True, db_index=True)

    system_generated = models.BooleanField(default=False)
    key = models.CharField(max_length=50, db_index=True)
    value = models.TextField()

    class Meta:
        unique_together = (
            ("txid", "wallet_hash", "key", "system_generated"),
        )
