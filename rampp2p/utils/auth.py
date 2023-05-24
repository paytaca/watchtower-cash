from django.core.signing import Signer
from django.core.exceptions import ValidationError
from rampp2p.models import Peer
from rampp2p import tasks

import logging
logger = logging.getLogger(__name__)

def verify_signature(wallet_hash, signature, message):
    '''
    Executes a javascript code to verify signature (maybe not the best way)
    '''
    logger.warn('simulating signature verification')
    # try:
    #     public_key = Peer.objects.values('public_key').get(wallet_hash=wallet_hash)['public_key']
    #     path = './rampp2p/escrow/src/'
    #     command = 'node {}signature.js verify {} {} {}'.format(
    #         path,
    #         public_key, 
    #         signature, 
    #         message
    #     )
    #     response = tasks.execute_subprocess(command)
    #     result = response.get('result')
    #     # error = response.get('error')

    #     is_valid = result.get('is_valid')
    #     if is_valid is None:
    #         is_valid = False
        
    #     if bool(is_valid) == False:
    #         raise ValidationError('invalid signature')
    # except Exception as err:
    #     raise ValidationError(err.args[0])
    return

def get_verification_headers(request):
    signature = request.headers.get('signature', None)
    timestamp = request.headers.get('timestamp', None)
    wallet_hash = request.headers.get('wallet-hash', None)
    if  (wallet_hash is None or
          signature is None or 
          timestamp is None):
        raise ValidationError('credentials not provided')
    return signature, timestamp, wallet_hash