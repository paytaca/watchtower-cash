import logging
from rest_framework import permissions
from django.conf import settings

LOGGER = logging.getLogger(__name__)

class IsCosigner(permissions.BasePermission):
    
    def has_permission(self, request, view):
        if getattr(settings, 'MULTISIG_AUTH', {}).get('ENABLE', False) == False:
            return True
        allow = False
        if request.user and hasattr(request.user, 'signer'):
            allow = True
        if len((view.kwargs or {}).keys()) == 0 and request.method == 'GET': # not accessing specific resource
            allow = True
        return allow