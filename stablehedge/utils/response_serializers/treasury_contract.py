from rest_framework import serializers

class TreasuryContractBchBalance(serializers.Serializer):
    total = serializers.IntegerField()
    spendable = serializers.IntegerField()
    utxo_count = serializers.IntegerField()

class TreasuryContractShortPayoutData(serializers.Serializer):
    count = serializers.IntegerField()
    total_nominal_units_x_sats_per_bch = serializers.IntegerField()
    total_sats_for_nominal_units_at_high_liquidation = serializers.IntegerField()

class TreasuryContractBalance(TreasuryContractBchBalance):
    short_payout_data = TreasuryContractShortPayoutData()
