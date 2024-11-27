from rest_framework import serializers

from .anyhedge import (
    ContractData,
    SettlementServiceSerializer,
    ShortProposalFundingAmounts,
)
from .transaction import (
    TransactionData,
    SignatureData,
)


class TreasuryContractMultiSigTx(TransactionData):
    funding_utxo_index = serializers.IntegerField(default=0)
    is_multisig = serializers.BooleanField(default=False)
    sig1 = SignatureData(many=True, read_only=True)
    sig2 = SignatureData(many=True, read_only=True)
    sig3 = SignatureData(many=True, read_only=True)


class ShortProposalData(serializers.Serializer):
    contract_data = ContractData(read_only=True)
    settlement_service = SettlementServiceSerializer(read_only=True)
    funding_amounts = ShortProposalFundingAmounts(read_only=True)
    funding_utxo_tx = TreasuryContractMultiSigTx(read_only=True)


class ShortProposalAccessKeys(serializers.Serializer):
    pubkey = serializers.CharField()
    signature = serializers.CharField()
