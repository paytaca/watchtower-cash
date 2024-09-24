from django.db import models
from django.contrib.postgres.fields import JSONField


class FiatToken(models.Model):
    category = models.CharField(max_length=64)
    genesis_supply = models.BigIntegerField(null=True, blank=True)

    decimals = models.IntegerField()
    currency = models.CharField(max_length=5, null=True, blank=True)

    def __str__(self):
        return f"FiatToken#{self.id}: {self.category}"


class RedemptionContract(models.Model):
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

    transaction_type = models.CharField(max_length=15)
    status = models.CharField(max_length=10, default=Status.PENDING)
    txid = models.CharField(max_length=64, null=True, blank=True)
    utxo = JSONField()
    result_message = models.CharField(max_length=100, null=True, blank=True)

    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
