from rest_framework import serializers

from anyhedge.serializers import SettlementServiceSerializer

class ShortProposalFundingAmounts(serializers.Serializer):
    short = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    long = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    liquidity_fee = serializers.IntegerField(read_only=True)
    recalculate_after = serializers.IntegerField(read_only=True)
    settlement_service_fee = serializers.IntegerField(read_only=True)
    satoshis_to_fund = serializers.IntegerField(read_only=True)

class ContractDataParameters(serializers.Serializer):
    maturityTimestamp = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    startTimestamp = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    highLiquidationPrice = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    lowLiquidationPrice = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    payoutSats = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    nominalUnitsXSatsPerBch = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    satsForNominalUnitsAtHighLiquidation = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    oraclePublicKey = serializers.CharField(read_only=True)
    longLockScript = serializers.CharField(read_only=True)
    shortLockScript = serializers.CharField(read_only=True)
    enableMutualRedemption = serializers.DecimalField(max_digits=1, decimal_places=0, read_only=True)
    longMutualRedeemPublicKey = serializers.CharField(read_only=True)
    shortMutualRedeemPublicKey = serializers.CharField(read_only=True)

class ContractDataMetadata(serializers.Serializer):
    takerSide = serializers.CharField(read_only=True)
    makerSide = serializers.CharField(read_only=True)
    shortPayoutAddress = serializers.CharField(read_only=True)
    longPayoutAddress = serializers.CharField(read_only=True)
    startingOracleMessage = serializers.CharField(read_only=True)
    startingOracleSignature = serializers.CharField(read_only=True)
    durationInSeconds = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    highLiquidationPriceMultiplier = serializers.FloatField(read_only=True)
    lowLiquidationPriceMultiplier = serializers.FloatField(read_only=True)
    isSimpleHedge = serializers.DecimalField(max_digits=1, decimal_places=0, read_only=True)
    startPrice = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    nominalUnits = serializers.FloatField(read_only=True)
    shortInputInOracleUnits = serializers.FloatField(read_only=True)
    longInputInOracleUnits = serializers.FloatField(read_only=True)
    shortInputInSatoshis = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    longInputInSatoshis = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    minerCostInSatoshis = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)

class ContractDataSettlement(serializers.Serializer):
    settlementTransactionHash = serializers.CharField(read_only=True)
    settlementType = serializers.CharField(read_only=True)
    settlementPrice = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    settlementMessage = serializers.CharField(read_only=True)
    settlementSignature = serializers.CharField(read_only=True)
    previousMessage = serializers.CharField(read_only=True)
    previousSignature = serializers.CharField(read_only=True)
    shortPayoutInSatoshis = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    longPayoutInSatoshis = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)

class ContractDataFunding(serializers.Serializer):
    fundingTransactionHash = serializers.CharField(read_only=True)
    fundingOutputIndex = serializers.DecimalField(max_digits=5, decimal_places=0, read_only=True)
    fundingSatoshis = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    settlement = ContractDataSettlement(read_only=True)

class ContractDataFee(serializers.Serializer):
    address = serializers.CharField(read_only=True)
    satoshis = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)

class ContractData(serializers.Serializer):
    address = serializers.CharField(read_only=True)
    version = serializers.CharField(read_only=True)

    parameters = ContractDataParameters(read_only=True)
    metadata = ContractDataMetadata(read_only=True)

    fundings = ContractDataFunding(many=True, read_only=True)
    fees = ContractDataFee(many=True, read_only=True)
