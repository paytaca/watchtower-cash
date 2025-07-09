import logging
from django.http import JsonResponse
from django.conf import settings
from django.urls import resolve

from multisig.utils import derive_pubkey_from_xpub
from .auth import (
    MultisigStatelessUser,
    get_timestamp_from_auth_data,
    is_valid_timestamp,
    parse_x_signature_header
)
from ..models import MultisigWallet, Signer

LOGGER = logging.getLogger(__name__)

class MultisigAuthMiddleware:
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if 'multisig' not in request.path:
            return self.get_response(request)

        public_key = request.headers.get('X-Auth-PubKey', '')
        message = request.headers.get('X-Auth-Message', '')
        signature = request.headers.get('X-Auth-Signature', '')
        if signature:
            signature = parse_x_signature_header(signature)
        if message:
            timestamp = message.split(':')[1]

            is_valid_timestamp(int(timestamp)) # short circuits if timestamp is > ±drift

        if not hasattr(request, 'resolver_match') or request.resolver_match == None:
            request.resolver_match = resolve(request.path_info)

        wallet_identifier = request.resolver_match.kwargs.get('wallet_identifier')
        proposal_identifier = request.resolver_match.kwargs.get('proposal_identifier')  
        
        wallet = None 
        signer = None

        if wallet_identifier:
            if wallet_identifier.isdigit():
                wallet = MultisigWallet.objects.prefetch_related('signers').filter(id = int(wallet_identifier)).first()
            else:
                wallet = MultisigWallet.objects.prefetch_related('signers').filter(locking_bytecode=wallet_identifier).first()
        elif proposal_identifier:
            if proposal_identifier.isdigit():
                wallet = MultisigWallet.objects.prefetch_related('signers').filter(multisigtransactionproposal__id=int(proposal_identifier)).first()
            else:
                wallet = MultisigWallet.objects.prefetch_related('signers').filter(multisigtransactionproposal__locking_bytecode=proposal_identifier).first()        
        
        user = MultisigStatelessUser(wallet=wallet)

        if wallet and public_key:
            for signer in wallet.signers.all():
                derived_public_key = derive_pubkey_from_xpub(signer.xpub, 0)
                if public_key == derived_public_key:
                    request.user.signer = signer
                    break 
                    
        user.wallet = wallet
        user.auth_data = {
            'public_key': public_key,
            'signature': signature,
            'message': message
        }
        request.user = user
        return self.get_response(request)
        
        