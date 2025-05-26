from rest_framework import serializers
from .wallet import MultisigWalletSerializer, SignerSerializer
from ..models.transaction_proposal import MultisigTransactionProposal, Signature

class SignatureSerializer(serializers.ModelSerializer):
    signer = serializers.PrimaryKeyRelatedField(read_only=True)
    transaction_proposal = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Signature
        fields = ['id', 'signer', 'transaction_proposal', 'input_index', 'signature_key', 'signature_value']
        read_only_fields = ['signers', 'created_at']

class MultisigTransactionProposalSerializer(serializers.ModelSerializer):
    wallet = serializers.PrimaryKeyRelatedField(read_only=True)
    signatures = SignatureSerializer(many=True, read_only=True)
    

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        signatures = {}
        for sig in instance.signatures.all():
            input_index = sig.input_index
            if input_index not in signatures:
                signatures[input_index] = {}
            signatures[input_index][sig.signature_key] = sig.signature_value
        
        request = self.context.get('request')
        if request:
            params = {k.lower(): v for k, v in request.query_params.items()}
            if params.get('expand_wallet') in ["1", "true", "yes", "on"]:
                rep['wallet'] = MultisigWalletSerializer(instance.wallet, context=self.context).data
        
        rep['signatures'] = signatures
        rep['sourceOutputs'] = rep.pop('source_outputs')

        return rep

    class Meta:
        model = MultisigTransactionProposal
        fields = ['id', 'wallet', 'transaction', 'source_outputs', 'metadata', 'created_at', 'signatures']
