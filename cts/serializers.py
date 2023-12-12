import requests
from typing import Dict
from rest_framework import serializers
from django.db.models import Q
from main.models import Transaction
from drf_yasg.utils import swagger_serializer_method


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

# Util get the authkey token id associated with an authguard
# token_authguard_addresses = [{<category or tokenId>: <authguard contract token deposit address> }, ...]
# authguard = The authguard address of the token_id we're looking for
def extract_token_id_from_tokenid_authguard_pair(token_authguard_addresses, authguard):

    def f(token_id__authguard__keypair): # token_id__authguard__keypair = {<category or tokenId>: <authguard contract token deposit address> 
        if authguard in token_id__authguard__keypair.values():
            return True 
        return False

    found = next(filter(f, token_authguard_addresses), None)
    return found

def extract_authguard_from_tokenid_authguard_pair(token_authguard_addresses, token_id):

    def f(token_id__authguard__keypair): # token_id__authguard__keypair = {<category or tokenId>: <authguard contract token deposit address> 
        if token_id__authguard__keypair.get(token_id):
            return True 
        return False

    found = next(filter(f, token_authguard_addresses), None)
    return found
    

class UtxoSerializer(serializers.Serializer):

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
    
    token = {
      'amount': 0,
      'commitment': ''
    }

    if obj.amount:
      if obj.amount > 9007199254740991:
        token['amount'] = str(obj.amount)
      else:
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

class AuthchainIdentitySerializer(UtxoSerializer):

  authGuard = serializers.SerializerMethodField()
  authGuardTokenId = serializers.SerializerMethodField()
  authKeyOwner = serializers.SerializerMethodField()
  authKey = serializers.SerializerMethodField()

  def get_authGuard(self, obj) -> str:
    return obj.authGuard

  def get_authKeyOwner(self, obj) -> str:
    return obj.authKeyOwner
  
  def get_authGuardTokenId(self, obj) -> str:
    token_id_authguard_pairs = self.context.get('token_id_authguard_pairs')
    authguard = self.get_authGuard(obj)
    if authguard and token_id_authguard_pairs:
      found = extract_token_id_from_tokenid_authguard_pair(token_id_authguard_pairs, authguard)
      return list(found.keys())[0] # key here is tokenId
    return None
  
  @swagger_serializer_method(serializer_or_field=serializers.DictField)
  def get_authKey(self, obj) -> Dict[str, str]:
    authkey_token_id = self.get_authGuardTokenId(obj)
    if authkey_token_id:
      authKey = Transaction.objects.filter(
          Q(spent=False) & 
          (Q(address__address=obj.authKeyOwner) | Q(address__token_address=obj.authKeyOwner)) &
          Q(cashtoken_nft__commitment='00') &
          Q(cashtoken_nft__category=authkey_token_id)
        ).first()
      if authKey:
        s = UtxoSerializer(authKey, many=False)
        return s.data

    return None
    
  class Meta:
    model = Transaction
    fields = ['txid','vout', 'satoshis', 'height', 'coinbase', 'token', 'authGuard', 'authKeyOwner', 'authKey', 'authGuardTokenId']


class AuthKeySerializer(UtxoSerializer):

  authGuard = serializers.SerializerMethodField()
  authKeyOwner = serializers.SerializerMethodField()
  unlockableTokens = serializers.SerializerMethodField()
  unlockableTokensCount = serializers.SerializerMethodField()

  def get_authGuard(self, obj) -> str:
    token_id_authguard_pairs = self.context.get('token_id_authguard_pairs')
    if obj.cashtoken_nft.category and token_id_authguard_pairs:
      found = extract_authguard_from_tokenid_authguard_pair(token_id_authguard_pairs, obj.cashtoken_nft.category)
      if found:
        return found[obj.cashtoken_nft.category] # key here is tokenId, value is the address
    return None

  def get_authKeyOwner(self, obj) -> str:
    return obj.authKeyOwner
  
  @swagger_serializer_method(serializer_or_field=serializers.DictField)
  def get_unlockableTokens(self, obj) -> Dict[str, str]:
    auth_guard = self.get_authGuard(obj)
    if auth_guard:
      tokens = Transaction.objects.filter(
          Q(spent=False) & 
          (Q(address__address=auth_guard) | Q(address__token_address=auth_guard))
        )
      if tokens:
        s = UtxoSerializer(tokens, many=True)
        return s.data

    return None
  
  def get_unlockableTokensCount(self, obj) -> int:
    c = self.get_unlockableTokens(obj)
    if c:
      return len(c)
    else:
      return 0
    
  class Meta:
    model = Transaction
    fields = ['txid','vout', 'satoshis', 'height', 'coinbase', 'token', 'authGuard', 'authKeyOwner', 'unlockableTokens', 'unlockableTokensCount']

class FungibleTokenBalanceSerializer(serializers.Serializer):

  owner = serializers.CharField()
  balance = serializers.CharField()
  tokenId = serializers.SerializerMethodField()
  utxoCount = serializers.IntegerField()

  def get_tokenId(self, obj):
    return obj.get('cashtoken_ft__category')

  class Meta:
    fields = ['owner', 'tokenId', 'balance', 'utxoCount']