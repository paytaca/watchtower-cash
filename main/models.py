from django.contrib.contenttypes.fields import GenericRelation, GenericForeignKey
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField
from psqlextra.models import PostgresModel
from psqlextra.query import PostgresQuerySet
from django.contrib.postgres.fields import ArrayField
from django.db.models.constraints import UniqueConstraint
from django.db.models import Q
from django.conf import settings
from datetime import date

from main.utils.address_validator import *
from main.utils.address_converter import *
import requests
import re
import uuid
import web3

from django.utils.crypto import get_random_string
from cryptography.fernet import Fernet
import random

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

    auth_token = models.CharField(max_length=200, unique=True, null=True)
    auth_nonce = models.CharField(max_length=6, null=True)

    last_balance_check = models.DateTimeField(null=True)
    last_utxo_scan_succeeded = models.BooleanField(null=True)

    def __str__(self):
        return self.wallet_hash

    def create_auth_token(self):
        token = get_random_string(40)
        cipher_suite = Fernet(settings.FERNET_KEY)
        self.auth_token = cipher_suite.encrypt(token.encode()).decode()
        self.save()

    def update_auth_nonce(self):
        self.auth_nonce = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        self.save()
    
    def save(self, *args, **kwargs):
        if not self.auth_token:
            self.auth_token = get_random_string(40)
        super().save(*args, **kwargs)

class Address(PostgresModel):
    address = models.CharField(max_length=100, unique=True, db_index=True)
    token_address = models.CharField(max_length=100, null=True, blank=True, db_index=True)
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
    address_path = models.CharField(max_length=10, db_index=True)
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
            elif is_bch_address(self.address) or is_token_address(self.address):
                if is_token_address(self.address):
                    self.address = bch_address_converter(self.address, to_token_addr=False)
                    self.token_address = self.address
                else:
                    self.token_address = bch_address_converter(self.address)

                wallet.wallet_type = 'bch'
            elif re.match("0x[0-9a-f]{40}", self.address, re.IGNORECASE):
                wallet.wallet_type = 'sbch'
            elif web3.Web3.isAddress(self.address):
                wallet.wallet_type = 'sbch'
            wallet.save()
        super(Address, self).save(*args, **kwargs)
        

class CashTokenInfo(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    symbol = models.CharField(max_length=100)
    decimals = models.PositiveIntegerField(default=0, null=True)
    image_url = models.URLField(blank=True, null=True)
    nft_details = JSONField(default=dict)


class CashFungibleToken(models.Model):
    category = models.CharField(
        max_length=100,
        unique=True,
        primary_key=True,
        db_index=True
    )
    info = models.ForeignKey(
        CashTokenInfo,
        related_name='fungible_tokens',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    class Meta:
        verbose_name_plural = 'CashToken Fungible Tokens'

    def __str__(self):
        if self.info:
            return f'{self.info.name} | {self.category[:7]}'
        else:
            return f'CashToken | {self.category[:7]}'

    @property
    def token_id(self):
        return f'ct/{self.category}'

    def get_info(self):
        info = self.info
        return {
            'id': self.token_id,
            'name': info.name,
            'symbol': info.symbol,
            'decimals': info.decimals,
            'image_url': info.image_url,
            'is_cashtoken': True
        }
    
    def fetch_metadata(self):
        PAYTACA_BCMR_URL = f'{settings.PAYTACA_BCMR_URL}/tokens/{self.category}/'
        response = requests.get(PAYTACA_BCMR_URL)
        if response.status_code == 200:
            data = response.json()
            if 'error' not in data.keys():
                uris = data.get('token').get('uris')
                if not uris:
                    uris = data.get('uris') or {'icon': None}

                try:
                    decimals = int(data.get('token').get('decimals'))
                except (TypeError, ValueError):
                    decimals = 0

                info, _ = CashTokenInfo.objects.get_or_create(
                    name=data.get('name', f'CT-{self.category[0:4]}'),
                    description=data.get('description', ''),
                    symbol=data.get('token').get('symbol'),
                    decimals=decimals,
                    image_url=uris.get('icon')
                )
                self.info = info
                self.save()


class CashNonFungibleTokenQuerySet(PostgresQuerySet):
    def filter_has_group(self, has_group=True):
        has_group_expr = models.Exists(
            CashNonFungibleToken.objects.filter(
                category=models.OuterRef("category"),
                capability=CashNonFungibleToken.Capability.MINTING,
            )
        )

        if has_group:
            return self.filter(has_group_expr)
        else:
            return self.filter(~has_group_expr)

    def filter_group(self):
        subquery = CashNonFungibleToken.objects \
            .filter(capability=CashNonFungibleToken.Capability.MINTING) \
            .values("category") \
            .annotate(latest_category_record_id=models.Max("id")) \
            .values("latest_category_record_id")
        return self.filter(id__in=subquery)

    def annotate_owner_address(self):
        owner_addr = Transaction.objects.filter(
            ~models.Q(cashtoken_nft__capability=CashNonFungibleToken.Capability.MINTING),
            cashtoken_nft_id=models.OuterRef("pk"),
            spent=False,
            amount__gte=0,
        ).values("address__address")[:1]
        return self.annotate(owner_address=owner_addr)

    def annotate_owner_wallet_hash(self):
        owner_wallet_hash = Transaction.objects.filter(
            cashtoken_nft_id=models.OuterRef("pk"),
            spent=False,
            amount__gte=0,
        ).values("wallet__wallet_hash")[:1]
        return self.annotate(owner_wallet_hash=owner_wallet_hash)


class CashNonFungibleToken(models.Model):
    objects = CashNonFungibleTokenQuerySet.as_manager()

    class Capability(models.TextChoices):
        MUTABLE = 'mutable'
        MINTING = 'minting'
        NONE = 'none'  # immutable

    category = models.CharField(max_length=100, db_index=True)
    commitment = models.CharField(max_length=255, default='', blank=True)
    capability = models.CharField(
        max_length=10,
        choices=Capability.choices,
        default='',
        blank=True
    )
    info = models.ForeignKey(
        CashTokenInfo,
        related_name='nfts',
        on_delete=models.CASCADE,
        blank=True,
        null=True
    )
    current_txid = models.CharField(max_length=70)
    current_index = models.PositiveIntegerField()

    class Meta:
        verbose_name_plural = 'CashToken NFTs'
        unique_together = (
            'current_index',
            'current_txid',
        )

    def __str__(self):
        if self.info:
            return f'{self.info.name} | {self.category[:7]}'
        else:
            return f'CashToken NFT | {self.category[:7]}'
        
    @property
    def token_id(self):
        return f'ct/{self.category}/{self.current_txid}/{self.current_index}'

    def get_info(self):
        info = self.info
        return {
            'id': self.token_id,
            'name': info.name,
            'symbol': info.symbol,
            'decimals': info.decimals,
            'image_url': info.image_url,
            'nft_details': info.nft_details,
            'is_cashtoken': True
        }

class Transaction(PostgresModel):
    txid = models.CharField(max_length=70, db_index=True)
    address = models.ForeignKey(
        Address,
        related_name='transactions',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    amount = models.BigIntegerField(
        null=True,
        blank=True,
        db_index=True
    )
    value = models.BigIntegerField(
        default=0,
        db_index=True
    )
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
    cashtoken_ft = models.ForeignKey(
        CashFungibleToken,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    cashtoken_nft = models.ForeignKey(
        CashNonFungibleToken,
        on_delete=models.CASCADE,
        null=True,
        blank=True
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
    post_save_processed = models.DateTimeField(null=True, blank=True)
    tx_timestamp = models.DateTimeField(null=True, blank=True, db_index=True)
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
    
    def get_token_decimals(self):
        decimals = None
        if self.token.tokenid == settings.WT_DEFAULT_CASHTOKEN_ID:
             if self.cashtoken_ft:
                 if self.cashtoken_ft.info:
                    decimals = self.cashtoken_ft.info.decimals
             if self.cashtoken_nft:
                 if self.cashtoken_nft.info:
                    decimals = self.cashtoken_nft.info.decimals
        else:
            decimals = self.token.decimals
        return decimals


class Recipient(PostgresModel):
    web_url = models.CharField(max_length=300, null=True, blank=True, db_index=True)
    telegram_id = models.CharField(max_length=50, null=True, blank=True, db_index=True)
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
            raw_pos_id = posid
            posid = int(posid)
            posid = str(posid)
            pad = "0" * (self.POS_ID_MAX_DIGITS-len(posid))
            posid = pad + posid
        except (ValueError, TypeError):
            posid = None
            raw_pos_id = None
    
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

        filter_arg = models.Q(senders__overlap=addresses_subquery) | models.Q(recipients__overlap=addresses_subquery)

        if raw_pos_id is not None:
            vault_payments = TransactionMetaAttribute.objects.filter(
                key=f'vault_payment_{raw_pos_id}',
                wallet_hash=wallet_hash
            ).values('txid')
            filter_arg |= Q(txid__in=vault_payments)

        return self.filter(filter_arg, wallet__wallet_hash=wallet_hash)

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
    # unlike SLP tokens, cashtoken NFTs and fungible tokens can be on the same txn
    # unlike SLP tokens, a single cashtoken txn can have multiple tokens of diff category (token ID)
    # thus, [wallet, txid] is not enough to make this model unique
    # token_index = models.PositiveIntegerField(default=0)
    record_type = models.CharField(
        max_length=10,
        blank=True,
        db_index=True,
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
    cashtoken_ft = models.ForeignKey(
        CashFungibleToken,
        on_delete=models.CASCADE,
        related_name='wallet_history_records',
        null=True,
        blank=True
    )
    cashtoken_nft = models.ForeignKey(
        CashNonFungibleToken,
        on_delete=models.CASCADE,
        related_name='wallet_history_records',
        null=True,
        blank=True
    )
    tx_fee = models.FloatField(null=True, blank=True)
    tx_timestamp = models.DateTimeField(null=True,blank=True, db_index=True)
    date_created = models.DateTimeField(default=timezone.now, db_index=True)

    usd_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    market_prices = JSONField(null=True, blank=True)

    class Meta:
        verbose_name = 'Wallet history'
        verbose_name_plural = 'Wallet histories'
        ordering = ['-tx_timestamp', '-date_created']
        constraints = [
            UniqueConstraint(
                fields=['wallet', 'txid', 'token', 'amount', 'record_type'],
                condition=Q(cashtoken_ft=None) & Q(cashtoken_nft=None),
                name='both_ctft_ctnft_none'
            ),
            UniqueConstraint(
                fields=['wallet', 'txid', 'token', 'amount', 'record_type', 'cashtoken_nft'],
                condition=Q(cashtoken_ft=None),
                name='ctft_none'
            ),
            UniqueConstraint(
                fields=['wallet', 'txid', 'token', 'amount', 'record_type', 'cashtoken_ft'],
                condition=Q(cashtoken_nft=None),
                name='ctnft_none'
            ),
            UniqueConstraint(
                fields=['wallet', 'txid', 'token', 'amount', 'record_type', 'cashtoken_ft', 'cashtoken_nft'],
                condition=Q(cashtoken_nft=None),
                name='ctft_ctnft_not_none'
            )
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
            market_price = float(self.usd_price)

        if not market_price:
            return

        return {
            "currency": currency,
            "value": round(market_price * self.amount, 2),
        }

    @property
    def usd_value(self):
        default_currency = "USD"
        usd_price = None
        if self.usd_price:
            usd_price = float(self.usd_price)
        elif self.market_prices and self.market_prices.get(default_currency, None):
            usd_price = self.market_prices[default_currency]

        if not usd_price:
            return

        return {
            "currency": default_currency,
            "value": round(usd_price * self.amount, 2),
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
    date_dispensed = models.DateTimeField(null=True, blank=True, db_index=True)
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
    currency = models.CharField(max_length=20, db_index=True)
    relative_currency = models.CharField(max_length=20, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    source = models.CharField(max_length=100, null=True, blank=True, db_index=True)

    price_value = models.DecimalField(max_digits=15, decimal_places=3)


class WalletPreferences(PostgresModel):
    wallet = models.OneToOneField(Wallet, on_delete=models.CASCADE, related_name="preferences")
    selected_currency = models.CharField(max_length=5, default="USD")
    wallet_name = models.CharField(max_length=75, blank=True)


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


class TransactionBroadcast(PostgresModel):
    txid = models.CharField(max_length=70, db_index=True)
    tx_hex = models.TextField()
    num_retries = models.IntegerField(default=0)
    date_received = models.DateTimeField(default=timezone.now)
    date_succeeded = models.DateTimeField(null=True, blank=True, db_index=True)
    error = models.TextField()

    def __str__(self):
        return self.txid

class WalletShard(PostgresModel):
    # stored as-is from client-side; revisit if needs more secure approach for storing
    shard = models.CharField(max_length=400, primary_key=True)
    first_identifier = models.CharField(max_length=64)
    second_identifier = models.CharField(max_length=64)

class AppVersion(models.Model):
    PLATFORM_CHOICES = [
        ('ios', 'iOS'),
        ('android', 'Android'),
        ('web', 'Web')
    ]

    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES)
    latest_version = models.CharField(max_length=10)
    min_required_version = models.CharField(max_length=10)
    release_date = models.DateField(default=date.today)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.platform} - Latest: {self.latest_version}, Min Required: {self.min_required_version}"
    
    class Meta:
        unique_together = ('platform', 'latest_version', 'min_required_version')


class WalletAddressApp(models.Model):

    app_name = models.TextField(blank=True, null=True, help_text='Name of the App/Dapp where the wallet_address was connected to')
    app_url  = models.TextField(blank=True, null=True, help_text='URL of the App/Dapp where the wallet_address was connected to')
    wallet_address  = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.wallet_address} -> {self.app_url}"
