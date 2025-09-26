import logging
from django.db import transaction
from rest_framework import serializers
from typing import Dict
from main.models import Transaction
from ..models.wallet import MultisigWallet, Signer
from ..utils import derive_pubkey_from_xpub
from ..js_client import get_wallet_hash

LOGGER = logging.getLogger(__name__)

class SignerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Signer
        fields = ['entity_key', 'xpub']

class MultisigWalletSerializer(serializers.ModelSerializer):
    signers = SignerSerializer(many=True, read_only=True)

    class Meta:
        model = MultisigWallet
        fields = ['id', 'name', 'm', 'signers', 'created_at']
        read_only_fields = ['signers', 'created_at']
    
    def create(self, validated_data):
        with transaction.atomic():
            signers = validated_data.get('signers')
            wallet_hash = get_wallet_hash({
               'name': validated_data.get('name'),
               'm': validated_data.get('m'),
               'signers': signers
            })

            wallet, created = MultisigWallet.objects.get_or_create(
                wallet_hash=wallet_hash,
                defaults= {
                    'm': validated_data.get('m'),
                    'name': validated_data.get('name'),
                    'wallet_hash': validated_data.get('wallet_hash')
                }
            )
            
            if created:
                request = self.context.get('request')
                for signer in signers:
                    signer = Signer.objects.get_or_create(
                        wallet=wallet,
                        xpub=signer['xpub'],
                        name=signer['name']
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