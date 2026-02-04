import logging
from django.db import transaction
from rest_framework import serializers
from typing import Dict
from main.models import Transaction
from ..models.wallet import MultisigWallet, Signer
from ..utils import derive_pubkey_from_xpub, get_multisig_wallet_locking_script

LOGGER = logging.getLogger(__name__)

class SignerSerializer(serializers.ModelSerializer):
    masterFingerprint = serializers.CharField(source='master_fingerprint')
    derivationPath = serializers.CharField(source='derivation_path')
    publicKey = serializers.CharField(source='public_key')
    walletDescriptor = serializers.CharField(source='wallet_descriptor')
    wallet = serializers.PrimaryKeyRelatedField(queryset=MultisigWallet.objects.all())

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
        ]


class MultisigWalletSerializer(serializers.ModelSerializer):

    walletDescriptorId = serializers.CharField(source='wallet_descriptor_id')
    walletHash = serializers.CharField(source='wallet_hash')
    signers = SignerSerializer(many=True, read_only=True)

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
            # Add any additional MultisigWallet fields you'd like to expose
        ]


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