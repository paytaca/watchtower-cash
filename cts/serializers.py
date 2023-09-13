from rest_framework import serializers
from main.models import Transaction
# from typing import TypedDict, Optional, Union

# const NFTCapability = {
#   none: literal("none"),
#   mutable: literal("mutable"),
#   minting: literal("minting"),
# };

# class TokenI(TypedDict):
#   amount: int
#   tokenId: str
#   capability: Optional[str]
#   commitment: Optional[str]

# class UtxoI(TypedDict):
#   txid: str
#   vout: int
#   satoshis: int
#   height: Optional[int]
#   coinbase: Optional[bool]
#   token: Optional[TokenI]

class UtxoSerializer(serializers.Serializer):

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

  def get_coinbase(self, obj):
    return False # We just assume watchtower is not indexing coinbase txs, verify.

  def get_token(self, obj):
    
    token = {}

    if obj.amount:
      token['amount'] = obj.amount

    if obj.cashtoken_ft and obj.cashtoken_ft.category:
      token['tokenId'] = obj.cashtoken_ft.category

    if obj.cashtoken_nft and not token.get('tokenId'):
      token['tokenId'] = obj.cashtoken_nft.category

    if obj.cashtoken_nft and obj.cashtoken_nft.commitment:
      token['commitment'] = obj.cashtoken_nft.commitment
    
    if obj.cashtoken_nft and obj.cashtoken_nft.capability:
      token['capability'] = obj.cashtoken_nft.capability
    
    if len(token.keys()) > 0:
      return token 
    
    return None

  class Meta:
    model = Transaction
    fields = ['txid','vout', 'satoshis', 'height', 'coinbase', 'token']

