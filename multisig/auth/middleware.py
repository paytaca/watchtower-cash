import logging
from .auth import is_valid_timestamp

LOGGER = logging.getLogger(__name__)

class MultisigAuthMiddleware:
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if 'multisig' not in request.path:
            return self.get_response(request)
        message = request.headers.get('X-Auth-Message', '')
        if message:
            timestamp = message.split(':')[1]
            is_valid_timestamp(int(timestamp)) # short circuits if timestamp is > ±drift
        return self.get_response(request)
        
        