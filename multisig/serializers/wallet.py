import logging
from django.db import transaction
from multisig.models.auth import ServerIdentity
from multisig.serializers.auth import  ServerIdentitySerializer
from rest_framework import serializers
from typing import Dict
from main.models import Transaction
from multisig.models.wallet import MultisigWallet, Signer, KeyRecord
from multisig.utils import derive_pubkey_from_xpub, get_multisig_wallet_locking_script

LOGGER = logging.getLogger(__name__)

class SignerSerializer(serializers.ModelSerializer):
    masterFingerprint = serializers.CharField(source='master_fingerprint')
    derivationPath = serializers.CharField(source='derivation_path')
    publicKey = serializers.CharField(source='public_key')
    walletDescriptor = serializers.CharField(source='wallet_descriptor')
    wallet = serializers.PrimaryKeyRelatedField(read_only=True)
    coordinatorKeyRecord = serializers.CharField(write_only=True)

    class Meta:
        model = Signer
        fields = [
            'id',
            'name',
            'masterFingerprint',
            'derivationPath',
            'publicKey',
            'walletDescriptor',
            'wallet',
            'coordinatorKeyRecord'
        ]

class MultisigWalletSerializer(serializers.ModelSerializer):
    signers = SignerSerializer(many=True, required=False)
    walletDescriptorId = serializers.CharField(source='wallet_descriptor_id')
    walletHash = serializers.CharField(source='wallet_hash')

    class Meta:
        model = MultisigWallet
        fields = [
            'id',
            'name',
            'walletHash',
            'walletDescriptorId',
            'version',
            'created_at',
            'deleted_at',
            'updated_at',
            'coordinator',
            'signers'
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'deleted_at'
        ]

    def create(self, validated_data):
        coordinator = self.context["coordinator"]
        signers_data = validated_data.pop("signers", [])
        wallet_descriptor_id = validated_data.get("wallet_descriptor_id")

        with transaction.atomic():
            wallet = MultisigWallet.objects.filter(
                coordinator=coordinator,
                wallet_descriptor_id=wallet_descriptor_id
            ).first()

            if wallet:
                return wallet

            wallet = MultisigWallet.objects.create(
                coordinator=coordinator,
                **validated_data
            )

            for signer_data in signers_data:
                signer_server_identity = ServerIdentity.objects.filter(public_key=signer_data['public_key']).first()
                coordinatorKeyRecordHex = signer_data.pop('coordinatorKeyRecord', None)
                
                if not signer_server_identity:
                    
                    server_identity_serializer = ServerIdentitySerializer(
                      data={'publicKey': signer_data['public_key']}
                    )

                    if server_identity_serializer.is_valid():
                      signer_server_identity = server_identity_serializer.save()
                      if coordinatorKeyRecordHex:
                        KeyRecord.objects.get_or_create(
                          publisher=coordinator,
                          recipient=signer_server_identity,
                          key_record=coordinatorKeyRecordHex,
                          defaults = {
                            'publisher': coordinator,
                            'recipient': signer_server_identity,
                            'key_record': coordinatorKeyRecordHex,
                          }
                        )
                        
                    else:
                        raise serializers.ValidationError(server_identity_serializer.errors)
                
                Signer.objects.create(
                    wallet=wallet,
                    server_identity=signer_server_identity,
                    **signer_data
                )

        return wallet

class MultisigWalletUtxoSerializer(serializers.Serializer):

  txid = serializers.CharField()
  vout = serializers.SerializerMethodField()
  satoshis = serializers.SerializerMethodField()
  height = serializers.SerializerMethodField()
  coinbase = serializers.SerializerMethodField()
  token = serializers.SerializerMethodField()

  def get_vout(self, obj):
    return obj.index

  def get_satoshis(self, obj):
    return obj.value

  def get_height(self, obj):
    if obj.blockheight:
      return obj.blockheight.number
    else:
      return 0

  def get_coinbase(self, obj) -> bool:
    return False # We just assume watchtower is not indexing coinbase txs, verify.

  def get_token(self, obj) -> Dict[str,str]:
    
    token = {}

    if obj.amount:
      token['amount'] = str(obj.amount)

    if obj.cashtoken_ft and obj.cashtoken_ft.category:
      token['category'] = obj.cashtoken_ft.category

    if obj.cashtoken_nft:
      if not token.get('category'):
        token['category'] = obj.cashtoken_nft.category
      token['nft'] = {
          'commitment': obj.cashtoken_nft.commitment,
          'capability': obj.cashtoken_nft.capability
      }
    if len(token.keys()) > 0:
      return token 
    
    return None

  class Meta:
    model = Transaction
    fields = ['txid','vout', 'satoshis', 'height', 'coinbase', 'token']


class KeyRecordSerializer(serializers.Serializer):
    publisher = serializers.PrimaryKeyRelatedField(queryset=ServerIdentity.objects.all(), required=False)
    recipient = serializers.PrimaryKeyRelatedField(queryset=ServerIdentity.objects.all(), required=False)
    key_record = serializers.CharField()

    class Meta:
        model = KeyRecord
        fields = ['id', 'publisher', 'recipient', 'key_record']