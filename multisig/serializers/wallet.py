import logging
from django.db import transaction
from rest_framework import serializers
from typing import Dict
from main.models import Transaction
from ..models.wallet import MultisigWallet, Signer
from ..utils import derive_pubkey_from_xpub, get_multisig_wallet_locking_script

LOGGER = logging.getLogger(__name__)

class SignerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Signer
        fields = ['entity_key', 'xpub']

class MultisigWalletSerializer(serializers.ModelSerializer):
    signers = SignerSerializer(many=True, read_only=True)
    lockingData = serializers.JSONField(source='locking_data')
    template = serializers.JSONField()

    class Meta:
        model = MultisigWallet
        fields = ['id', 'template', 'lockingData', 'signers', 'created_at', 'locking_bytecode']
        read_only_fields = ['signers', 'created_at']
    
    def create(self, validated_data):
        locking_data = validated_data.get('locking_data', {})
        template = validated_data.get('template', {})
        with transaction.atomic():
            locking_bytecode = get_multisig_wallet_locking_script(template, locking_data)
            wallet, created = MultisigWallet.objects.get_or_create(
                locking_bytecode=locking_bytecode,
                defaults= {
                    'template': template,
                    'locking_data':locking_data,
                    'locking_bytecode':locking_bytecode    
                }
            )
            
            if created:
                hd_public_keys = locking_data.get('hdKeys', {}).get('hdPublicKeys', {})
                request = self.context.get('request')
                for key, value in hd_public_keys.items():
                    signer = Signer.objects.create(
                        wallet=wallet,
                        entity_key=key,
                        xpub=value
                    )
                    if request:
                      uploader_pubkey = request.headers.get('X-Auth-PubKey')
                      derived_public_key = derive_pubkey_from_xpub(signer.xpub, 0)
                      if uploader_pubkey == derived_public_key:
                         wallet.created_by = signer
                         wallet.save(update_fields=['created_by'])
            else:
                if wallet.deleted_at:
                    wallet.deleted_at = None
                    wallet.save(updated_fields=['deleted_at'])
                    
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