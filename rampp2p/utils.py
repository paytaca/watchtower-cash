from django.core.signing import Signer
from django.core.exceptions import ValidationError
from django.conf import settings
import subprocess

def verify_signature(wallet_hash, pubkey, signature, message):
    print('verify_signature')
    # signer = Signer(pubkey)
    # try:
    #     signed_message = signer.unsign(signature)
    #     if signed_message != message:
    #         raise ValidationError('Signature is invalid')
    # except:
    #     raise ValidationError('Signature is invalid')  

    # TODO: derive the address from the public key
    # TODO: address must be registered under the Wallet with field wallet_hash=wallet_hash

def get_verification_headers(request):
  pubkey = request.headers.get('pubkey', None)
  signature = request.headers.get('signature', None)
  timestamp = request.headers.get('timestamp', None)
  wallet_hash = request.headers.get('wallet-hash', None)
  if  wallet_hash is None or pubkey is None or signature is None or timestamp is None:
    raise ValidationError('credentials not provided')
  return pubkey, signature, timestamp, wallet_hash

# Escrow(bytes20 arbiter, bytes20 buyer, bytes20 seller, bytes20 servicer, int tradingFee, int arbitrationFee)
class Contract():
    def __init__(self, arbiterPk, buyerPk, sellerPk):
        self.arbiterPk = arbiterPk
        self.buyerPk = buyerPk
        self.sellerPk = sellerPk
        self.servicerPk = settings.SERVICER_PK
        self.tradingFee = int(settings.TRADING_FEE)
        self.arbitrationFee = int(settings.ARBITRATION_FEE)
        self.address = self.generate_contract(
            self.arbiterPk, 
            self.buyerPk, 
            self.sellerPk, 
            self.servicerPk,
            self.tradingFee,
            self.arbitrationFee
        )
    
    def generate_contract(self, arbiterPk, buyerPk, sellerPk, servicerPk, tradingFee, arbitrationFee):
        path = './rampp2p/escrow/src/'
        command = 'node {}escrow.js contract {} {} {} {} {} {}'.format(
           path,
           arbiterPk, 
           sellerPk, 
           buyerPk,
           servicerPk,
           tradingFee,
           arbitrationFee
        )
        process = subprocess.Popen(command.split(), stdout=subprocess.PIPE)
        # capture the output and errors
        output, error = process.communicate()  
        if error is not None:
           raise ContractError(error.decode('utf-8'))
        return output.decode('utf-8')
        
def escrow_funds(data):
  pass

def escrow_release(data):
  pass

def escrow_refund(data):
  pass

class ContractError(Exception):
    def __init__(self, message):
        self.message = message
    
    def __str__(self):
        return self.message