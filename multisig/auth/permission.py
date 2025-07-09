import logging
from rest_framework import permissions
from django.conf import settings

LOGGER = logging.getLogger(__name__)

class IsCosigner(permissions.BasePermission):
    
    def has_permission(self, request, view):
        if not getattr(settings, 'MULTISIG_AUTH', {}).get('ENABLE'):
            return True
        allow = False
        if request.user and request.user.signer:
            allow = True
        if len((view.kwargs or {}).keys()) == 0 and request.method == 'GET': # not accessing specific resource
            allow = True
        return allow