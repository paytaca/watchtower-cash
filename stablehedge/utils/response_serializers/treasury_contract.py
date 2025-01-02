from rest_framework import serializers

class TreasuryContractBchBalance(serializers.Serializer):
    total = serializers.IntegerField()
    spendable = serializers.IntegerField()
    utxo_count = serializers.IntegerField()

class TreasuryContractShortPositionValue(serializers.Serializer):
    count = serializers.IntegerField()
    satoshis = serializers.IntegerField()
    unit_value = serializers.IntegerField()

class TreasuryContractBalance(TreasuryContractBchBalance):
    in_short = TreasuryContractShortPositionValue()