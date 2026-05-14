import logging
from django.db import transaction
from rest_framework import serializers
from .wallet import MultisigWalletSerializer, SignerSerializer
from ..models.transaction_proposal import MultisigTransactionProposal, Signature
from ..models.wallet import Signer
LOGGER = logging.getLogger(__name__)

class SignatureSerializer(serializers.ModelSerializer):
    signer = serializers.PrimaryKeyRelatedField(read_only=True)
    transactionProposal = serializers.PrimaryKeyRelatedField(source='transaction_proposal', read_only=True)
    inputIndex = serializers.IntegerField(source='input_index')
    sigKey = serializers.CharField(source='signature_key')
    sigValue = serializers.CharField(source='signature_value')

    class Meta:
        model = Signature
        fields = ['id', 'signer', 'transactionProposal', 'inputIndex', 'sigKey', 'sigValue']
        read_only_fields = ['id', 'transactionProposal']

class MultisigTransactionProposalSerializer(serializers.ModelSerializer):
    wallet = serializers.PrimaryKeyRelatedField(read_only=True)
    signatures = SignatureSerializer(many=True)
    sourceOutputs = serializers.JSONField(source='source_outputs')
    transactionHash = serializers.CharField(source='transaction_hash')
    createdAt = serializers.CharField(source='created_at', read_only=True)
    broadcastStatus = serializers.CharField(source='broadcast_status', read_only=True)
  
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get('request')
        if request:
            params = {k.lower(): v for k, v in request.query_params.items()}
            if params.get('expand_wallet') in ["1", "true", "yes", "on"]:
                rep['wallet'] = MultisigWalletSerializer(instance.wallet, context=self.context).data
        rep['signatures'] = SignatureSerializer(instance.signatures.all(), many=True).data
        return rep

    def create(self, validated_data):
        signatures_data = validated_data.pop('signatures', [])
        with transaction.atomic():
            proposal = MultisigTransactionProposal.objects.create(**validated_data)
            for sig_data in signatures_data:
                for entity in proposal.wallet.template['entities'].items():
                    variable = sig_data['signature_key'].split('.')[0]
                    signer, signer_entity_data = entity
                    if signer_entity_data['variables'].get(variable):
                        signer = Signer.objects.get(wallet=proposal.wallet, entity_key=signer)
                        Signature.objects.create(transaction_proposal=proposal, signer=signer, **sig_data)
       
        return proposal


    class Meta:
        model = MultisigTransactionProposal
        fields = ['id', 'wallet', 'origin', 'purpose',  'transaction', 'transactionHash', 'sourceOutputs', 'metadata', 'createdAt', 'signatures', 'broadcastStatus']
