import logging
import json
from django.db import transaction
from multisig.serializers.wallet import SignerSerializer
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

import multisig.js_client as js_client
from multisig.models.transaction import Bip32Derivation, Proposal, Input, Psbt, Signature

LOGGER = logging.getLogger(__name__)

class InputSerializer(serializers.ModelSerializer):
    proposal = serializers.PrimaryKeyRelatedField(read_only=True)
    outpointTransactionHash = serializers.CharField(source='outpoint_transaction_hash')
    outpointIndex = serializers.IntegerField(source='outpoint_index')
    redeemScript = serializers.CharField(source='redeem_script', read_only=True, allow_blank=True, allow_null=True)
    spendingTxid = serializers.CharField(source='spending_txid', read_only=True, allow_blank=True, allow_null=True)
    conflictingProposalIdentifier = serializers.CharField(source='conflicting_proposal_identifier', read_only=True, allow_blank=True, allow_null=True)
    
    class Meta:
        model = Input
        fields = ['id', 'proposal', 'outpointTransactionHash', 'outpointIndex', 'redeemScript', 'spendingTxid', 'conflictingProposalIdentifier']
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
    status = serializers.CharField(read_only=True)
    coordinator = SignerSerializer(read_only=True)
    combinedPsbt = serializers.CharField(source='combined_psbt', read_only=True)

    class Meta:
        model = Proposal
        fields = [
            'id', 'wallet', 'proposal', 'proposalFormat', 'combinedPsbt',
            'unsignedTransactionHex', 'unsignedTransactionHash',
            'signedTransaction', 'signedTransactionHash', 'txid',
            'signingProgress', 'coordinator', 'status'
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        # rep['inputs'] = InputSerializer(instance.inputs.all(), many=True).data
        filtered_rep = {k: v for k, v in rep.items() if v not in [None, '', [], {}]}
        return filtered_rep

    def create(self, validated_data):
        coordinator = self.context["coordinator"]
        with transaction.atomic():
            proposal_format = validated_data.get('proposal_format') or 'psbt'
            if proposal_format == 'psbt':
                decode_response = js_client.decode_psbt(validated_data['proposal'])
                decode_response.raise_for_status()
                decoded_proposal = decode_response.json()
                signing_progress = decoded_proposal.get('signingProgress', {})

                inputs = decoded_proposal.pop('inputs', [])
                decoded_proposal.pop('signingProgress', None) 
                proposal, created= Proposal.objects.get_or_create(
                    unsigned_transaction_hex=decoded_proposal.get('unsignedTransactionHex'),
                    deleted_at__isnull=True,
                    defaults={
                        'wallet': validated_data.get('wallet'),
                        'unsigned_transaction_hex': decoded_proposal.get('unsignedTransactionHex'),
                        'proposal': validated_data['proposal'],
                        'proposal_format': proposal_format,
                        'coordinator': coordinator
                    }
                )

                if created:
                    psbt = None
                    if signing_progress.get('signingProgress', '') and signing_progress.get('signingProgress', '') != 'unsigned':
                        psbt = Psbt.objects.create(
                            proposal=proposal,
                            content=validated_data['proposal'],
                            is_proposal=True
                        )

                    for input in inputs:
                        input_model = Input.objects.create(
                            proposal=proposal,
                            outpoint_transaction_hash=input.get('outpointTransactionHash'),
                            outpoint_index=input.get('outpointIndex'),
                            redeem_script=input.get('redeemScript')
                        )
                        signatures = input.get('signatures', {})
                        bip32_derivation = input.get('bip32Derivation', {})
                        for pub_key, derivation in bip32_derivation.items():
                                # Avoid double creation if already handled above for a pubkey that is also in 'signatures'
                                Bip32Derivation.objects.get_or_create(
                                    input=input_model,
                                    public_key=pub_key,
                                    defaults={
                                        'path': derivation.get('path'),
                                        'master_fingerprint': derivation.get('masterFingerprint'),
                                    }
                                )
                                
                        for public_key, signature in signatures.items():
                            if not bip32_derivation.get(public_key):
                                raise ValidationError(f"BIP32 derivation data is missing for public key: {public_key}")

                            Signature.objects.get_or_create(
                                input=input_model,
                                public_key=public_key,
                                defaults={
                                    'input': input_model,
                                    'psbt': psbt,
                                    'public_key': public_key,
                                    'signature': signature
                                }
                            )
                return proposal

    def update(self, instance, validated_data):
        return super().update(instance, validated_data)


class ProposalCoordinatorSerializer(serializers.ModelSerializer):
    coordinator = SignerSerializer(read_only=True)

    class Meta:
        model = Proposal
        fields = ['id', 'coordinator']
        read_only_fields = ['id', 'coordinator']

class PsbtSerializer(serializers.ModelSerializer):
    standard = serializers.CharField(default='psbt')
    encoding = serializers.CharField(default='base64')
    content = serializers.CharField()
    contentHash = serializers.CharField(source='content_hash', read_only=True)
    proposal = serializers.PrimaryKeyRelatedField(read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    isProposal = serializers.BooleanField(source='is_proposal', read_only=True)

    class Meta:
        model = Psbt
        fields = ['id', 'proposal', 'content', 'standard', 'encoding', 'contentHash', 'createdAt', 'isProposal']
        read_only_fields = ['id', 'proposal', 'createdAt', 'contentHash', 'isProposal']

    def create(self, validated_data):

        with transaction.atomic():
            standard = validated_data.get('standard') or 'psbt'
            if standard == 'psbt':
                decode_response = js_client.decode_psbt(validated_data['content'])
                decode_response.raise_for_status()
                decoded_proposal = decode_response.json()
                decoded_proposal.pop('signingProgress', None) 
                proposal = validated_data.get('proposal')
                psbt = None
                content_hash = Psbt.compute_content_hash(validated_data['content'])

                psbt, created = Psbt.objects.get_or_create(
                    content_hash=content_hash,
                    defaults={
                        'proposal': proposal,
                        'content': validated_data['content'],
                        'standard': standard,
                        'encoding': validated_data.get('encoding') or 'base64',
                    }
                )

                if not created:
                    return psbt

                response = js_client.combine_psbts([proposal.combined_psbt, validated_data['content']])
                response.raise_for_status()
                response_json = response.json()
                LOGGER.info(f"response.json {response_json}")
                LOGGER.info(f"combined PSBT: {response_json.get('result')}")
                if response_json.get('result'):
                    proposal.combined_psbt = response_json.get('result')
                    proposal.save(update_fields=["combined_psbt"])

                inputs = decoded_proposal.pop('inputs', [])

                for input in inputs:
                    input_model = Input.objects.filter(
                        proposal_id=proposal.id,
                        outpoint_transaction_hash=input.get('outpointTransactionHash'),
                        outpoint_index=input.get('outpointIndex'),
                        redeem_script=input.get('redeemScript')
                    ).first()

                    if not input_model:
                        raise ValidationError(f"Signed an input that's not part of the proposal")

                    signatures = input.get('signatures', {})
                    bip32_derivation = input.get('bip32Derivation', {})
                    
                    for public_key in signatures.keys():
                        if not bip32_derivation.get(public_key):
                            raise ValidationError(f"BIP32 derivation data is missing for public key: {public_key}")

                        Signature.objects.get_or_create(
                            input=input_model,
                            public_key=public_key,
                            signature=signatures[public_key],
                            defaults={
                                'input': input_model,
                                'psbt': psbt,
                                'public_key': public_key,
                                'signature': signatures[public_key]
                            }
                        )

            return psbt

class Bip32DerivationSerializer(serializers.ModelSerializer):
    """Read-only serializer for BIP32 derivation (path, publicKey, masterFingerprint)."""
    publicKey = serializers.CharField(source='public_key', read_only=True)
    masterFingerprint = serializers.CharField(source='master_fingerprint', read_only=True, allow_null=True)

    class Meta:
        model = Bip32Derivation
        fields = ['id', 'path', 'publicKey', 'masterFingerprint']
        read_only_fields = ['id', 'path', 'publicKey', 'masterFingerprint']


class SignatureSerializer(serializers.ModelSerializer):
    """Read-only serializer; hydrates the related Input."""
    input = InputSerializer(read_only=True)
    publicKey = serializers.CharField(source='public_key', read_only=True)
    psbt = serializers.PrimaryKeyRelatedField(read_only=True, allow_null=True)

    class Meta:
        model = Signature
        fields = ['id', 'input', 'publicKey', 'signature', 'psbt']
        read_only_fields = ['id', 'input', 'publicKey', 'signature', 'psbt']


class SignatureWithBip32Serializer(serializers.ModelSerializer):
    """Read-only serializer returning signature, publicKey, input, bip32Derivation."""
    publicKey = serializers.CharField(source='public_key', read_only=True)
    input = InputSerializer(read_only=True)
    bip32Derivation = serializers.SerializerMethodField()

    class Meta:
        model = Signature
        fields = ['signature', 'publicKey', 'input', 'bip32Derivation']

    def get_bip32Derivation(self, obj):
        # Use prefetched input.bip32_derivation when available to avoid N+1
        derivations = getattr(obj.input, 'bip32_derivation', None)
        if derivations is None:
            derivation = Bip32Derivation.objects.filter(
                input=obj.input,
                public_key=obj.public_key,
            ).first()
        else:
            derivation = next(
                (d for d in derivations.all() if d.public_key == obj.public_key),
                None,
            )
        if derivation is None:
            return None
        return Bip32DerivationSerializer(derivation).data
