import logging
from django.db import transaction
from rest_framework import serializers

import multisig.js_client as js_client
from multisig.models.transaction import Proposal, Input, SigningSubmission

LOGGER = logging.getLogger(__name__)

class InputSerializer(serializers.ModelSerializer):
    proposal = serializers.PrimaryKeyRelatedField(read_only=True)
    outpointTransactionHash = serializers.CharField(source='outpoint_transaction_hash')
    outpointIndex = serializers.IntegerField(source='outpoint_index')

    class Meta:
        model = Input
        fields = ['id', 'proposal', 'outpointTransactionHash', 'outpointIndex']
        read_only_fields = ['id', 'proposal']


class ProposalSerializer(serializers.ModelSerializer):
    proposal = serializers.CharField(required=True)
    proposalFormat = serializers.CharField(source='proposal_format', default='psbt', required=False, allow_blank=True)
    unsignedTransactionHex = serializers.CharField(source='unsigned_transaction_hex', read_only=True)
    unsignedTransactionHash = serializers.CharField(source='unsigned_transaction_hash', read_only=True)
    signedTransaction = serializers.CharField(source='signed_transaction', read_only=True)
    signedTransactionHash = serializers.CharField(source='signed_transaction_hash', read_only=True)
    txid = serializers.CharField(read_only=True)
    signingProgress = serializers.CharField(source='signing_progress', read_only=True)
    broadcastStatus = serializers.CharField(source='broadcast_status', read_only=True)

    class Meta:
        model = Proposal
        fields = [
            'id', 'wallet', 'proposal', 'proposalFormat',
            'unsignedTransactionHex', 'unsignedTransactionHash',
            'signedTransaction', 'signedTransactionHash', 'txid',
            'signingProgress', 'broadcastStatus'
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        # rep['inputs'] = InputSerializer(instance.inputs.all(), many=True).data
        filtered_rep = {k: v for k, v in rep.items() if v not in [None, '', [], {}]}
        return filtered_rep

    def create(self, validated_data):
        with transaction.atomic():
            if validated_data.get('proposal_format') == 'psbt':
                decode_response = js_client.decode_proposal(validated_data['proposal'], validated_data['proposal_format'])
                decode_response.raise_for_status()
                decoded_proposal = decode_response.json()
                inputs = decoded_proposal.pop('inputs', []) 

                proposal, created= Proposal.objects.get_or_create(
                    unsigned_transaction_hex=decoded_proposal.get('unsigned_transaction_hex'),
                    defaults={
                        'wallet': validated_data.get('wallet'),
                        'proposal': validated_data['proposal'],
                        'proposal_format': validated_data['proposal_format'],
                    }
                )
                if created:
                    for input in inputs:
                        Input.objects.create(
                            proposal=proposal,
                            outpoint_transaction_hash=input.get('outpoint_transaction_hash'),
                            outpoint_index=input.get('outpoint_index'),
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
