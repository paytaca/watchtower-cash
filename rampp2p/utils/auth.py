from django.core.signing import Signer
from django.core.exceptions import ValidationError
from rampp2p.models import Peer
from rampp2p import tasks

import logging
logger = logging.getLogger(__name__)

def verify_signature(wallet_hash, signature, message):
    
    # load the public key
    public_key = Peer.objects.values('public_key').get(wallet_hash=wallet_hash)['public_key']

    # execute the subprocess
    path = './rampp2p/escrow/src/'
    command = 'node {}signature.js {} {} {}'.format(
        path,
        public_key, 
        signature, 
        message
    )
    result = tasks.execute_subprocess(command)
    logger.warning(f'result: {result}')
    return result

def get_verification_headers(request):
    signature = request.headers.get('signature', None)
    timestamp = request.headers.get('timestamp', None)
    wallet_hash = request.headers.get('wallet-hash', None)
    if  (wallet_hash is None or
          signature is None or 
          timestamp is None):
        raise ValidationError('credentials not provided')
    return signature, timestamp, wallet_hash