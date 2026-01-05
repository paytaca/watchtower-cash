from rest_framework import serializers

class TreasuryContractBchBalance(serializers.Serializer):
    total = serializers.IntegerField()
    spendable = serializers.IntegerField()
    utxo_count = serializers.IntegerField()

class TreasuryContractShortPositionValue(serializers.Serializer):
    count = serializers.IntegerField()
    satoshis = serializers.IntegerField()
    unit_value = serializers.IntegerField()

class TreasuryContractShortPayoutData(serializers.Serializer):
    total_nominal_units_x_sats_per_bch = serializers.DecimalField(max_digits=20, decimal_places=8)
    total_sats_for_nominal_units_at_high_liquidation = serializers.DecimalField(max_digits=20, decimal_places=8)

class TreasuryContractBalance(TreasuryContractBchBalance):
    in_short = TreasuryContractShortPositionValue()
    short_payout_data = TreasuryContractShortPayoutData()
