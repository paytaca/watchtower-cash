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

    short_wallet_hash = models.CharField(max_length=75, db_index=True)
    short_address = models.CharField(max_length=75)
    short_pubkey = models.CharField(max_length=75)
    short_address_path = models.CharField(max_length=10, null=True, blank=True)
    long_wallet_hash = models.CharField(max_length=75, db_index=True)
    long_address = models.CharField(max_length=75)
    long_pubkey = models.CharField(max_length=75)
    long_address_path = models.CharField(max_length=10, null=True, blank=True)

    oracle_pubkey = models.CharField(max_length=75)

    start_price = models.IntegerField()
    low_liquidation_multiplier = models.FloatField()
    high_liquidation_multiplier = models.FloatField()

    starting_oracle_message = models.CharField(max_length=40)
    starting_oracle_signature = models.CharField(max_length=130)

    # low_liquidation_price = models.IntegerField()
    # high_liquidation_price = models.IntegerField()

    funding_tx_hash = models.CharField(max_length=75, null=True, blank=True, db_index=True)
    funding_tx_hash_validated = models.BooleanField(default=False)

    short_funding_proposal = models.OneToOneField(
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

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.CharField(max_length=5, null=True, blank=True)

    class Meta:
        ordering = ['-start_timestamp']

    def __str__(self):
        return f"<HedgePosition#{self.id}: {self.address}>"

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
    def total_sats_with_fee(self):
        total_sats = self.total_sats
        for fee in self.fees.all():
            total_sats += fee.satoshis
        return total_sats

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

    @property
    def price_oracle_message(self):
        if getattr(self, "_price_oracle_message", None):
            price_oracle_message = self._price_oracle_message
            if price_oracle_message.pubkey == self.oracle_pubkey and price_oracle_message.message_timestamp == self.start_timestamp:
                return price_oracle_message

        self._price_oracle_message = PriceOracleMessage.objects.filter(
            pubkey=self.oracle_pubkey,
            message_timestamp=self.start_timestamp,
        ).first()
        return self._price_oracle_message
        

class HedgePositionMetadata(models.Model):
    POSITION_TAKER_SHORT = "short"
    POSITION_TAKER_LONG = "long"
    POSITION_TAKERS = [POSITION_TAKER_SHORT, POSITION_TAKER_LONG]
    POSITION_TAKERS = [(pos, pos) for pos in POSITION_TAKERS]

    hedge_position = models.OneToOneField(HedgePosition, on_delete=models.CASCADE, related_name="metadata")

    position_taker = models.CharField(choices=POSITION_TAKERS, null=True, blank=True, max_length=5) # synonymous to what position the user took
    liquidity_fee = models.IntegerField(null=True, blank=True) # with respect to `position_taker`
    network_fee = models.IntegerField(null=True, blank=True) # total tx fees for funding and settlement
    total_short_funding_sats = models.IntegerField(null=True, blank=True)
    total_long_funding_sats = models.IntegerField(null=True, blank=True)


class HedgeSettlement(models.Model):
    hedge_position = models.ForeignKey(HedgePosition, on_delete=models.CASCADE, related_name="settlements")

    spending_transaction = models.CharField(max_length=75, db_index=True)
    settlement_type = models.CharField(max_length=20)
    short_satoshis = models.BigIntegerField()
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
    short_signature = models.TextField(null=True, blank=True)
    long_signature = models.TextField(null=True, blank=True)

    auth_token = models.TextField(null=True, blank=True)


class HedgePositionFunding(models.Model):
    # should be required but set to nullable for backward compatibility
    hedge_position = models.ForeignKey(
        HedgePosition,
        on_delete=models.CASCADE,
        related_name="fundings",
        null=True, blank=True,
    )
    tx_hash = models.CharField(max_length=75, db_index=True)
    funding_output = models.IntegerField(default=-1)
    funding_satoshis = models.BigIntegerField(default=-1)
    validated = models.BooleanField(default=False)

    settlement = models.OneToOneField(
        HedgeSettlement,
        related_name="funding",
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )


class HedgePositionFee(models.Model):
    hedge_position = models.ForeignKey(HedgePosition, on_delete=models.CASCADE, related_name="fees")
    name = models.CharField(max_length=100, default="")
    description = models.TextField(default="")

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


    POSITION_SHORT = "short"
    POSITION_LONG = "long"
    POSITIONS = [POSITION_SHORT, POSITION_LONG]
    POSITIONS = [(pos, pos) for pos in POSITIONS]

    initiator = models.CharField(max_length=5, default=POSITION_SHORT, choices=POSITIONS)
    hedge_position = models.OneToOneField(HedgePosition, on_delete=models.CASCADE, related_name="mutual_redemption")
    redemption_type = models.CharField(max_length=20, choices=REDEMPTION_TYPES)
    short_satoshis = models.BigIntegerField()
    long_satoshis = models.BigIntegerField()
    short_schnorr_sig = models.TextField(null=True, blank=True)
    long_schnorr_sig = models.TextField(null=True, blank=True)
    settlement_price = models.IntegerField(null=True, blank=True)

    # existence of this data would imply it is executed already
    tx_hash = models.CharField(max_length=75, null=True, blank=True)
    # added a reference to funding tx to resolve mapping between fundings & settlements
    funding_tx_hash = models.CharField(max_length=75, null=True, blank=True)


class HedgePositionOffer(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_SETTLED = "settled"

    STATUSES = [
        STATUS_PENDING,
        STATUS_ACCEPTED,
        STATUS_SETTLED,
    ]

    STATUSES = [(STATUS, STATUS.replace('_', ' ').capitalize()) for STATUS in STATUSES]

    POSITION_SHORT = "short"
    POSITION_LONG = "long"
    POSITIONS = [
        POSITION_SHORT,
        POSITION_LONG,
    ]
    POSITIONS = [(POSITION, POSITION.replace('_', ' ').capitalize()) for POSITION in POSITIONS]
    status = models.CharField(max_length=15, choices=STATUSES, default=STATUS_PENDING)

    position = models.CharField(max_length=5, choices=POSITIONS, null=True, blank=True)
    wallet_hash = models.CharField(max_length=100, db_index=True)
    satoshis = models.BigIntegerField()

    duration_seconds = models.IntegerField()
    high_liquidation_multiplier = models.FloatField()
    low_liquidation_multiplier = models.FloatField()

    oracle_pubkey = models.CharField(max_length=75, default='')
    address = models.CharField(max_length=75)
    pubkey = models.CharField(max_length=75)
    address_path = models.CharField(max_length=10, default='')

    hedge_position = models.OneToOneField(
        HedgePosition,
        related_name="position_offer",
        on_delete=models.CASCADE,
        null=True, blank=True,
        db_index=True,
    )

    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_counter_party_info(self):
        try:
            return self.counter_party_info
        except HedgePositionOffer.counter_party_info.RelatedObjectDoesNotExist:
            pass


class HedgePositionOfferCounterParty(models.Model):
    """
    Contains information that is not provided in HedgePositionOffer,
    but is needed to create a contract

    This is used during "accepted" to "settled" phase of HedgePositionOffer
    """
    hedge_position_offer = models.OneToOneField(
        HedgePositionOffer,
        on_delete=models.CASCADE,
        related_name="counter_party_info"
    )

    contract_address = models.CharField(max_length=75, unique=True, db_index=True)
    anyhedge_contract_version = models.CharField(max_length=20)

    wallet_hash = models.CharField(max_length=100)
    address = models.CharField(max_length=75)
    pubkey = models.CharField(max_length=75)
    address_path = models.CharField(max_length=10)

    price_message_timestamp = models.DateTimeField()
    price_value = models.IntegerField()
    oracle_message_sequence = models.IntegerField()

    starting_oracle_message = models.CharField(max_length=40)
    starting_oracle_signature = models.CharField(max_length=130)

    settlement_service_fee = models.IntegerField(default=0)
    settlement_service_fee_address = models.CharField(max_length=75, default='')

    settlement_deadline = models.DateTimeField(null=True, blank=True)

    @property
    def price_oracle_message(self):
        pubkey = self.hedge_position_offer.oracle_pubkey
        message_sequence = self.oracle_message_sequence

        if getattr(self, "_price_oracle_message", None):
            price_oracle_message = self._price_oracle_message
            if price_oracle_message.pubkey == pubkey and price_oracle_message.message_sequence == message_sequence:
                return price_oracle_message

        self._price_oracle_message = PriceOracleMessage.objects.filter(
            pubkey=pubkey,
            message_sequence=message_sequence,
        ).first()
        return self._price_oracle_message

class Oracle(models.Model):
    active = models.BooleanField(default=True)

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
