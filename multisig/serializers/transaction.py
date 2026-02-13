import logging
import json
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

import multisig.js_client as js_client
from multisig.models.transaction import Bip32Derivation, Proposal, Input, Signature, SigningSubmission

LOGGER = logging.getLogger(__name__)

class InputSerializer(serializers.ModelSerializer):
    proposal = serializers.PrimaryKeyRelatedField(read_only=True)
    outpointTransactionHash = serializers.CharField(source='outpoint_transaction_hash')
    outpointIndex = serializers.IntegerField(source='outpoint_index')
    redeemScript = serializers.CharField(source='redeem_script', read_only=True, allow_blank=True, allow_null=True)

    class Meta:
        model = Input
        fields = ['id', 'proposal', 'outpointTransactionHash', 'outpointIndex', 'redeemScript']
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
            'signingProgress', 'broadcastStatus', 'coordinator'
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
                    defaults={
                        'wallet': validated_data.get('wallet'),
                        'unsigned_transaction_hex': decoded_proposal.get('unsignedTransactionHex'),
                        'proposal': validated_data['proposal'],
                        'proposal_format': proposal_format,
                        'coordinator': coordinator
                    }
                )

                if created:
                    signing_submission = None
                    if signing_progress.get('signingProgress', '') and signing_progress.get('signingProgress', '') != 'unsigned':
                        signing_submission = SigningSubmission.objects.create(
                            proposal=proposal,
                            payload=validated_data['proposal'],
                            payload_format=proposal_format,
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
                        LOGGER.info(input)
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
                                    'signing_submission': signing_submission,
                                    'public_key': public_key,
                                    'signature': signature
                                }
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
        fields = ['id', 'proposal', 'payload', 'payloadFormat', 'createdAt']
        read_only_fields = ['id', 'proposal', 'createdAt']

    def create(self, validated_data):
        LOGGER.info(validated_data)

        with transaction.atomic():
            format = validated_data.get('payload_format') or 'psbt'
            if format == 'psbt':
                decode_response = js_client.decode_psbt(validated_data['payload'])
                decode_response.raise_for_status()
                decoded_proposal = decode_response.json()
                decoded_proposal.pop('signingProgress', None) 
                proposal = validated_data.get('proposal')
                signing_submission = None
                payload_hash = SigningSubmission.compute_payload_hash(validated_data['payload'])

                signing_submission, created = SigningSubmission.objects.get_or_create(
                    payload_hash=payload_hash,
                    defaults={
                        'proposal': proposal,
                        'payload': validated_data['payload'],
                        'payload_format': format
                    }
                )

                if not created:
                    return signing_submission

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
                                'signing_submission': signing_submission,
                                'public_key': public_key,
                                'signature': signatures[public_key]
                            }
                        )
                    
                        

            return signing_submission

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
    signingSubmission = serializers.PrimaryKeyRelatedField(
        source='signing_submission', read_only=True, allow_null=True
    )

    class Meta:
        model = Signature
        fields = ['id', 'input', 'publicKey', 'signature', 'signingSubmission']
        read_only_fields = ['id', 'input', 'publicKey', 'signature', 'signingSubmission']


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


# class SigningSubmissionSerializer(serializers.ModelSerializer):
#     payloadFormat = serializers.CharField(source='payload_format', default='psbt')
#     createdAt = serializers.DateTimeField(source='created_at', read_only=True)
#     proposal = serializers.PrimaryKeyRelatedField(read_only=True)

#     class Meta:
#         model = SigningSubmission
#         fields = ['id', 'proposal', 'payload', 'payloadFormat', 'createdAt']
#         read_only_fields = ['id', 'proposal', 'createdAt']

#     def create(self, validated_data):
#         signing_submission = SigningSubmission.objects.create(**validated_data)

#         if signing_submission.payload_format == 'psbt':
#             resp = js_client.decode_psbt(signing_submission.payload)
#             resp.raise_for_status()
#             decoded = resp.json()

#             if not decoded.get('unsignedTransactionHash'):
#                 return signing_submission

#             proposal = Proposal.objects.filter(unsigned_transaction_hex=decoded.get('unsignedTransactionHash')).first()
#             if not proposal:
#                 return signing_submission

#             # Example pseudo-structure – adjust keys to match `decode_psbt` output
#             multisig_tx = ...  # MultisigTransactionProposal instance
#             for input_index, input_data in enumerate(decoded.get('inputs', [])):
#                 for sig in input_data.get('signatures', []):
#                     signer = ...  # lookup `Signer` from pubkey/fingerprint in sig
#                     Signature.objects.create(
#                         transaction_proposal=multisig_tx,
#                         signer=signer,
#                         input_index=input_index,
#                         signature_key=sig['key'],    # e.g. "key1.schnorr_signature.alloutputs"
#                         signature_value=sig['value'],  # actual signature
#                     )

#         return signing_submission