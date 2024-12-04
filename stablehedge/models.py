from django.db import models
from django.apps import apps
from django.contrib.postgres.fields import JSONField

from psqlextra.query import PostgresQuerySet


class FiatToken(models.Model):
    category = models.CharField(max_length=64)
    genesis_supply = models.BigIntegerField(null=True, blank=True)

    decimals = models.IntegerField()
    currency = models.CharField(max_length=5, null=True, blank=True)

    def __str__(self):
        return f"FiatToken#{self.id}: {self.category}"


class RedemptionContractQueryset(PostgresQuerySet):
    def annotate_redeemable(self):
        Transaction = apps.get_model("main", "Transaction")
        subquery = Transaction.objects.filter(
            address__address=models.OuterRef("address"),
            cashtoken_ft__category=models.OuterRef("fiat_token__category"),
            spent=False,
        ) \
            .order_by(models.F("value").desc(nulls_last=True)) \
            .values("value")[:1]

        return self.annotate(redeemable=subquery - models.Value(1000))

    def annotate_reserve_supply(self):
        Transaction = apps.get_model("main", "Transaction")
        subquery = Transaction.objects.filter(
            address__address=models.OuterRef("address"),
            cashtoken_ft__category=models.OuterRef("fiat_token__category"),
            spent=False,
        ) \
            .order_by(models.F("amount").desc(nulls_last=True)) \
            .values("amount")[:1]

        return self.annotate(reserve_supply=subquery)

    def annotate_is_subscribed(self):
        Subscription = apps.get_model("main", "Subscription")
        subquery = models.Exists(
            Subscription.objects.filter(address__address=models.OuterRef("address"))
        )
        return self.annotate(is_subscribed=subquery)


class RedemptionContract(models.Model):
    objects = RedemptionContractQueryset.as_manager()

    address = models.CharField(max_length=100)

    fiat_token = models.ForeignKey(FiatToken, on_delete=models.PROTECT, related_name="redemption_contracts")
    auth_token_id = models.CharField(max_length=64)
    price_oracle_pubkey = models.CharField(max_length=70)

    def __str__(self):
        return f"RedemptionContract#{self.id}: {self.address}"

    @property
    def network(self):
        if self.address.startswith("bchtest:"):
            return "chipnet"
        else:
            return "mainnet"

    @property
    def contract_opts(self):
        p2sh20_length = 54 if self.network == "mainnet" else 50
        address_type = "p2sh20" if len(self.address) <= p2sh20_length else "p2sh32"

        return dict(
            params=dict(
                authKeyId=self.auth_token_id,
                tokenCategory=self.fiat_token.category,
                oraclePublicKey=self.price_oracle_pubkey,
            ),
            options=dict(
                network=self.network,
                addressType=address_type,
            ),
        )

    @property
    def treasury_contract_address(self):
        try:
            self.treasury_contract
            return self.treasury_contract.address
        except self.__class__.treasury_contract.RelatedObjectDoesNotExist:
            pass

    def get_subscription(self):
        Subscription = apps.get_model("main", "Subscription")
        return Subscription.objects.filter(address__address=self.address).first()

    @property
    def is_subscribed(self):
        if not hasattr(self, "_is_subscribed"):
            return bool(self.get_subscription())
        return self._is_subscribed

    @is_subscribed.setter
    def is_subscribed(self, value):
        self._is_subscribed = value


class RedemptionContractTransaction(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        SUCCESS = "success"
        FAILED = "failed"

    class Type(models.TextChoices):
        DEPOSIT = "deposit"
        INJECT = "inject"
        REDEEM = "redeem"

    redemption_contract = models.ForeignKey(
        RedemptionContract, on_delete=models.PROTECT,
        related_name="transactions",
        null=True, blank=True,
    )
    price_oracle_message = models.ForeignKey(
        "anyhedge.PriceOracleMessage", on_delete=models.PROTECT,
        related_name="transactions",
        null=True, blank=True,
    )

    wallet_hash = models.CharField(max_length=70, null=True, blank=True)

    transaction_type = models.CharField(max_length=15)
    status = models.CharField(max_length=10, default=Status.PENDING)
    txid = models.CharField(max_length=64, null=True, blank=True)
    utxo = JSONField()
    result_message = models.TextField(null=True, blank=True)

    retry_count = models.IntegerField(default=0)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class TreasuryContractQuerySet(PostgresQuerySet):
    def annotate_is_subscribed(self):
        Subscription = apps.get_model("main", "Subscription")
        subquery = models.Exists(
            Subscription.objects.filter(address__address=models.OuterRef("address"))
        )
        return self.annotate(is_subscribed=subquery)


class TreasuryContract(models.Model):
    objects = TreasuryContractQuerySet.as_manager()

    redemption_contract = models.OneToOneField(
        RedemptionContract, on_delete=models.PROTECT,
        related_name="treasury_contract",
    )

    address = models.CharField(max_length=100)

    auth_token_id = models.CharField(max_length=64)

    pubkey1 = models.CharField(max_length=70)
    pubkey2 = models.CharField(max_length=70)
    pubkey3 = models.CharField(max_length=70)
    pubkey4 = models.CharField(max_length=70)
    pubkey5 = models.CharField(max_length=70)

    encrypted_funding_wif = models.CharField(
        max_length=200, unique=True,
        null=True, blank=True,
        help_text="Add prefix 'bch-wif:', if data is not encrypted"
    )

    def __str__(self):
        return f"TreasuryContract#{self.id}: {self.address}"

    @property
    def network(self):
        if self.address.startswith("bchtest:"):
            return "chipnet"
        else:
            return "mainnet"

    @property
    def contract_opts(self):
        p2sh20_length = 54 if self.network == "mainnet" else 50
        address_type = "p2sh20" if len(self.address) <= p2sh20_length else "p2sh32"

        return dict(
            params=dict(
                authKeyId=self.auth_token_id,
                pubkeys=[
                    self.pubkey1,
                    self.pubkey2,
                    self.pubkey3,
                    self.pubkey4,
                    self.pubkey5,
                ],
            ),
            options=dict(
                network=self.network,
                addressType=address_type,
            ),
        )

    def get_subscription(self):
        Subscription = apps.get_model("main", "Subscription")
        return Subscription.objects.filter(address__address=self.address).first()

    @property
    def is_subscribed(self):
        if not hasattr(self, "_is_subscribed"):
            return bool(self.get_subscription())
        return self._is_subscribed

    @is_subscribed.setter
    def is_subscribed(self, value):
        self._is_subscribed = value

    @property
    def pubkeys(self):
        return [
            self.pubkey1,
            self.pubkey2,
            self.pubkey3,
            self.pubkey4,
            self.pubkey5,
        ]


class TreasuryContractKey(models.Model):
    treasury_contract = models.OneToOneField(TreasuryContract, on_delete=models.CASCADE)
    pubkey1_wif = models.CharField(
        max_length=200, null=True, blank=True,
        help_text="Add prefix 'bch-wif:', if data is not encrypted"
    )
    pubkey2_wif = models.CharField(
        max_length=200, null=True, blank=True,
        help_text="Add prefix 'bch-wif:', if data is not encrypted"
    )
    pubkey3_wif = models.CharField(
        max_length=200, null=True, blank=True,
        help_text="Add prefix 'bch-wif:', if data is not encrypted"
    )
    pubkey4_wif = models.CharField(
        max_length=200, null=True, blank=True,
        help_text="Add prefix 'bch-wif:', if data is not encrypted"
    )
    pubkey5_wif = models.CharField(
        max_length=200, null=True, blank=True,
        help_text="Add prefix 'bch-wif:', if data is not encrypted"
    )
