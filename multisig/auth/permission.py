import logging
from multisig.auth.auth import parse_x_signature_header
from multisig.js_client import verify_signature
from multisig.utils import derive_pubkey_from_xpub
from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from django.conf import settings

LOGGER = logging.getLogger(__name__)

class IsCosigner(permissions.BasePermission):
    
    def has_permission(self, request, view):
        if getattr(settings, 'MULTISIG', {}).get('ENABLE_AUTH', False) == False:
            return True
        allow = False
        if request.user and hasattr(request.user, 'signer'):
            allow = True
        if len((view.kwargs or {}).keys()) == 0 and request.method == 'GET': # not accessing specific resource
            allow = True
        return allow
    
class IsCosignerOfNewMultisigWallet(permissions.BasePermission):

    def has_permission(self, request, view):
        if getattr(settings, 'MULTISIG', {}).get('ENABLE_AUTH', False) == False:
            return True
        
        message = request.headers.get('X-Auth-Message', '')
        public_key = request.headers.get('X-Auth-PubKey', '')
        signature = request.headers.get('X-Auth-Signature', '')

        if not signature or not message or not public_key:
            return False
        
        multisig_wallet = request.data
        auth_credential_public_key_is_cosigner = False

        for signer in multisig_wallet.get('signers', []):
            if signer.get('xpub') is None:
                raise ValidationError('Malformed multisig wallet signers')
            
            derived_public_key = derive_pubkey_from_xpub(signer['xpub'], 0)
            if public_key == derived_public_key:
                auth_credential_public_key_is_cosigner = True
                break
        
        if not auth_credential_public_key_is_cosigner:
            return False
        
        signature = parse_x_signature_header(signature)
        sig_verification_response = verify_signature(message, public_key, signature)
        sig_verification_result = sig_verification_response.json()
        if sig_verification_result['success']:
            return True
        
        return False