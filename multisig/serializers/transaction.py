from django.db import transaction
from rest_framework import serializers

from multisig.models.transaction import Proposal, Input, SigningSubmission
from main.utils.queries.bchn import BCHN

bchn = BCHN()

class InputSerializer(serializers.ModelSerializer):
    proposal = serializers.PrimaryKeyRelatedField(read_only=True)
    outpointTransactionHash = serializers.CharField(source='outpoint_transaction_hash')
    outpointIndex = serializers.IntegerField(source='outpoint_index')

    class Meta:
        model = Input
        fields = ['id', 'proposal', 'outpointTransactionHash', 'outpointIndex']
        read_only_fields = ['id', 'proposal']


class ProposalSerializer(serializers.ModelSerializer):
    purpose = serializers.CharField(required=False, allow_blank=True)
    origin = serializers.CharField(required=False, allow_blank=True)
    unsignedTransactionHex = serializers.CharField(source='unsigned_transaction_hex')
    unsignedTransactionHash = serializers.CharField(source='unsigned_transaction_hash', read_only=True)
    signedTransaction = serializers.CharField(source='signed_transaction', read_only=True)
    signedTransactionHash = serializers.CharField(source='signed_transaction_hash', read_only=True)
    txid = serializers.CharField(read_only=True)
    signingProgress = serializers.CharField(source='signing_progress', read_only=True)
    broadcastStatus = serializers.CharField(source='broadcast_status', read_only=True)
    inputs = InputSerializer(many=True, read_only=True)

    class Meta:
        model = Proposal
        fields = [
            'id', 'wallet', 'purpose', 'origin',
            'unsignedTransactionHex', 'unsignedTransactionHash',
            'signedTransaction', 'signedTransactionHash', 'txid',
            'signingProgress', 'broadcastStatus', 'inputs'
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['inputs'] = InputSerializer(instance.inputs.all(), many=True).data
        return rep

    def create(self, validated_data):
        decoded = bchn._decode_raw_transaction(validated_data['unsigned_transaction_hex'])
        with transaction.atomic():
            proposal = Proposal.objects.create(**validated_data)
            for item in decoded.get('vin', []):
                outpoint = item.get('txid')
                index = item.get('vout')
                Input.objects.create(
                    proposal=proposal,
                    outpoint_transaction_hash=outpoint,
                    outpoint_index=index,
                )
        return proposal

    def update(self, instance, validated_data):
        return super().update(instance, validated_data)


class SigningSubmissionSerializer(serializers.ModelSerializer):
    payloadFormat = serializers.CharField(source='payload_format', default='psbt')
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    proposal = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = SigningSubmission
        fields = ['id', 'signer', 'proposal', 'payload', 'payloadFormat', 'createdAt']
        read_only_fields = ['id', 'proposal', 'createdAt']
