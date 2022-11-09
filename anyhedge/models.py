from django.db import models
from django.contrib.postgres.fields import ArrayField

# Create your models here.
class HedgePositionQuerySet(models.QuerySet):
    class Annotations:
        low_liquidation_price = models.ExpressionWrapper(
            models.functions.Round(models.F("start_price") * models.F("low_liquidation_multiplier")),
            output_field=models.BigIntegerField()
        )
        high_liquidation_price = models.ExpressionWrapper(
            models.functions.Round(models.F("start_price") * models.F("high_liquidation_multiplier")),
            output_field=models.BigIntegerField()
        )
        nominal_unit_sats = models.ExpressionWrapper(
            models.functions.Round(models.F("start_price") * models.F("satoshis")),
            output_field=models.BigIntegerField()
        )
        total_sats = models.ExpressionWrapper(
            nominal_unit_sats / low_liquidation_price,
            output_field=models.BigIntegerField()
        )

        long_sats = total_sats - models.F("satoshis")
        long_unit_sats = models.ExpressionWrapper(
            long_sats * models.F("start_price"),
            output_field=models.BigIntegerField()
        )


class LongAccount(models.Model):
    wallet_hash = models.CharField(max_length=100, unique=True, db_index=True)
    address_path = models.CharField(max_length=10)
    address = models.CharField(max_length=75)
    pubkey = models.CharField(max_length=75)

    # balance = models.BigIntegerField(null=True, blank=True)

    min_auto_accept_duration = models.IntegerField(default=0)
    max_auto_accept_duration = models.IntegerField(default=0)
    auto_accept_allowance = models.BigIntegerField(default=0)


class HedgeFundingProposal(models.Model):
    tx_hash = models.CharField(max_length=75)
    tx_index = models.IntegerField()
    tx_value = models.BigIntegerField()
    script_sig = models.TextField()

    pubkey = models.CharField(max_length=75, default="")
    input_tx_hashes = ArrayField(
        base_field=models.CharField(max_length=75),
        null=True,
        blank=True,
    )


class HedgePosition(models.Model):
    objects = HedgePositionQuerySet.as_manager()

    address = models.CharField(max_length=75, unique=True, db_index=True)
    anyhedge_contract_version = models.CharField(max_length=20)

    satoshis = models.BigIntegerField()

    start_timestamp = models.DateTimeField()
    maturity_timestamp = models.DateTimeField()

    hedge_wallet_hash = models.CharField(max_length=75, db_index=True)
    hedge_address = models.CharField(max_length=75)
    hedge_pubkey = models.CharField(max_length=75)
    hedge_address_path = models.CharField(max_length=10, null=True, blank=True)
    long_wallet_hash = models.CharField(max_length=75, db_index=True)
    long_address = models.CharField(max_length=75)
    long_pubkey = models.CharField(max_length=75)
    long_address_path = models.CharField(max_length=10, null=True, blank=True)

    oracle_pubkey = models.CharField(max_length=75)

    start_price = models.IntegerField()
    low_liquidation_multiplier = models.FloatField()
    high_liquidation_multiplier = models.FloatField()

    # low_liquidation_price = models.IntegerField()
    # high_liquidation_price = models.IntegerField()

    funding_tx_hash = models.CharField(max_length=75, null=True, blank=True, db_index=True)
    funding_tx_hash_validated = models.BooleanField(default=False)

    hedge_funding_proposal = models.OneToOneField(
        HedgeFundingProposal,
        related_name="hedge_position",
        on_delete=models.CASCADE,
        null=True, blank=True,
    )
    long_funding_proposal = models.OneToOneField(
        HedgeFundingProposal,
        related_name="long_position",
        on_delete=models.CASCADE,
        null=True, blank=True,
    )

    class Meta:
        ordering = ['-start_timestamp']


    @property
    def low_liquidation_price(self):
        return round(self.start_price * self.low_liquidation_multiplier)

    @property
    def high_liquidation_price(self):
        return round(self.start_price * self.high_liquidation_multiplier)

    @property
    def total_sats(self):
        return round(round(self.satoshis * self.start_price) / self.low_liquidation_price)

    @property
    def long_input_sats(self):
        return self.total_sats - self.satoshis

    @property
    def nominal_units(self):
        return (self.satoshis * self.start_price) / 10 ** 8

    @property
    def duration_seconds(self):
        return (self.maturity_timestamp - self.start_timestamp).total_seconds() 

    def get_hedge_position_funding(self):
        if not self.funding_tx_hash:
            return

        return HedgePositionFunding.objects.filter(tx_hash=self.funding_tx_hash).first()

    @property
    def funding(self):
        return self.get_hedge_position_funding()

class HedgePositionMetadata(models.Model):
    POSITION_TAKER_HEDGE = "hedge"
    POSITION_TAKER_LONG = "long"
    POSITION_TAKERS = [POSITION_TAKER_HEDGE, POSITION_TAKER_LONG]
    POSITION_TAKERS = [(pos, pos) for pos in POSITION_TAKERS]

    hedge_position = models.OneToOneField(HedgePosition, on_delete=models.CASCADE, related_name="metadata")

    position_taker = models.CharField(choices=POSITION_TAKERS, null=True, blank=True, max_length=5) # synonymous to what position the user took
    liqiudidty_fee = models.IntegerField(null=True, blank=True) # with respect to `position_taker`
    network_fee = models.IntegerField(null=True, blank=True) # total tx fees for funding and settlement
    total_hedge_funding_sats = models.IntegerField(null=True, blank=True)
    total_long_funding_sats = models.IntegerField(null=True, blank=True)


class HedgeSettlement(models.Model):
    hedge_position = models.OneToOneField(HedgePosition, on_delete=models.CASCADE, related_name="settlement")

    spending_transaction = models.CharField(max_length=75, db_index=True)
    settlement_type = models.CharField(max_length=20)
    hedge_satoshis = models.BigIntegerField()
    long_satoshis = models.BigIntegerField()

    oracle_pubkey = models.CharField(max_length=75)
    settlement_price = models.IntegerField(null=True, blank=True)
    settlement_price_sequence = models.IntegerField(null=True, blank=True)
    settlement_message_sequence = models.IntegerField(null=True, blank=True)
    settlement_message_timestamp = models.DateTimeField(null=True, blank=True)
    settlement_message = models.CharField(max_length=40, null=True, blank=True)
    settlement_signature = models.CharField(max_length=130, null=True, blank=True)


# usable when hedge position is using an external settlement service
class SettlementService(models.Model):
    hedge_position = models.OneToOneField(HedgePosition, on_delete=models.CASCADE, related_name="settlement_service")
    domain = models.CharField(max_length=50)
    scheme = models.CharField(max_length=10)
    port = models.IntegerField()

    # settlement service requires signature and pubkey to access api
    # e.g. <scheme>://<domain>:<port>/status/?contractAddress=<address>&signature<hedge_signature>&pubkey=<hedge_pubkey>
    # generating signature is done here 
    # https://gitlab.com/GeneralProtocols/anyhedge/library/-/blob/v0.14.2/lib/anyhedge.ts#L399
    hedge_signature = models.TextField(null=True, blank=True)
    long_signature = models.TextField(null=True, blank=True)

    auth_token = models.TextField(null=True, blank=True)


class HedgePositionFunding(models.Model):
    tx_hash = models.CharField(max_length=75, db_index=True)
    funding_output = models.IntegerField()
    funding_satoshis = models.BigIntegerField()
    fee_output = models.IntegerField(null=True, blank=True)
    fee_satoshis = models.IntegerField(null=True, blank=True)


class HedgePositionFee(models.Model):
    hedge_position = models.OneToOneField(HedgePosition, on_delete=models.CASCADE, related_name="fee")
    address = models.CharField(max_length=75)
    satoshis = models.IntegerField()


class MutualRedemption(models.Model):
    TYPE_REFUND = 'refund'
    TYPE_EARLY_MATURATION = 'early_maturation'
    TYPE_ARBITRARY = 'arbitrary' 
    REDEMPTION_TYPES = [
        TYPE_REFUND,
        TYPE_EARLY_MATURATION,
        TYPE_ARBITRARY,
    ]
    REDEMPTION_TYPES = [(REDEMPTION_TYPE, REDEMPTION_TYPE.replace('_', ' ').capitalize()) for REDEMPTION_TYPE in REDEMPTION_TYPES]

    hedge_position = models.OneToOneField(HedgePosition, on_delete=models.CASCADE, related_name="mutual_redemption")
    redemption_type = models.CharField(max_length=20, choices=REDEMPTION_TYPES)
    hedge_satoshis = models.BigIntegerField()
    long_satoshis = models.BigIntegerField()
    hedge_schnorr_sig = models.TextField(null=True, blank=True)
    long_schnorr_sig = models.TextField(null=True, blank=True)
    settlement_price = models.IntegerField(null=True, blank=True)

    # existence of this data would imply it is executed already
    tx_hash = models.CharField(max_length=75, null=True, blank=True)


class HedgePositionOffer(models.Model):
    STATUS_PENDING = "pending"
    STATUS_SETTLED = "settled"
    STATUS_CANCELLED = "cancelled"

    STATUSES = [
        STATUS_PENDING,
        STATUS_SETTLED,
        STATUS_CANCELLED,
    ]

    STATUSES = [(STATUS, STATUS.replace('_', ' ').capitalize()) for STATUS in STATUSES]
    status = models.CharField(max_length=15, choices=STATUSES, default=STATUS_PENDING)

    wallet_hash = models.CharField(max_length=100, db_index=True)
    satoshis = models.BigIntegerField()

    duration_seconds = models.IntegerField()
    high_liquidation_multiplier = models.FloatField()
    low_liquidation_multiplier = models.FloatField()

    oracle_pubkey = models.CharField(max_length=75, null=True, blank=True)
    hedge_address = models.CharField(max_length=75)
    hedge_pubkey = models.CharField(max_length=75)
    hedge_address_path = models.CharField(max_length=10, null=True, blank=True)

    hedge_position = models.OneToOneField(
        HedgePosition,
        related_name="position_offer",
        on_delete=models.CASCADE,
        null=True, blank=True,
        db_index=True,
    )

    auto_settled = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Oracle(models.Model):
    pubkey = models.CharField(max_length=75, unique=True)
    relay = models.CharField(max_length=50)
    port = models.IntegerField()
    asset_name = models.CharField(max_length=25, db_index=True)
    asset_currency = models.CharField(max_length=10, default='')
    asset_decimals = models.IntegerField(default=0)


class PriceOracleMessage(models.Model):
    pubkey = models.CharField(max_length=75, db_index=True)
    signature = models.CharField(max_length=130)
    message = models.CharField(max_length=40)
    message_timestamp = models.DateTimeField(db_index=True)
    price_value = models.IntegerField()
    price_sequence = models.IntegerField(db_index=True)
    message_sequence = models.IntegerField(db_index=True)

    class Meta:
        ordering = ['-message_timestamp']
