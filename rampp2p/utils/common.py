from django.core.signing import Signer
from django.core.exceptions import ValidationError
from rampp2p.models import Order, Peer, TradeType

def get_order_peers(order: Order):
    # if order.ad is SELL, ad owner is seller
    # else order owner is seller
    seller = None
    buyer = None
    arbiter = order.arbiter
    if order.ad.trade_type == TradeType.SELL:
        seller = order.ad.owner
        buyer = order.owner
    else:
        seller = order.owner
        buyer = order.ad.owner
    
    return arbiter, buyer, seller

def verify_signature(wallet_hash, pubkey, signature, message):
    pass
    # pubkey = Peer.objects.values('public_key').get(wallet_hash=wallet_hash)['public_key']
    # signer = Signer(pubkey)
    # try:
    #     signed_message = signer.unsign(signature)
    #     if signed_message != message:
    #         raise ValidationError('Signature is invalid')
    # except:
    #     raise ValidationError('Signature is invalid')

def get_verification_headers(request):
    signature = request.headers.get('signature', None)
    timestamp = request.headers.get('timestamp', None)
    wallet_hash = request.headers.get('wallet-hash', None)
    if  (wallet_hash is None or
          signature is None or 
          timestamp is None):
        raise ValidationError('credentials not provided')
    return signature, timestamp, wallet_hash