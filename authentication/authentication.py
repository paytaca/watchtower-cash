# authentication.py

import hashlib

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import ApiToken


class ApiTokenAuthentication(BaseAuthentication):
    header_name = "X-API-Key"

    def authenticate(self, request):
        token_uuid = request.headers.get(self.header_name)

        if not token_uuid:
            return None

        api_token = ApiToken.objects.filter(uuid=token_uuid).first()
        if api_token:
            request.api_token = api_token
        return None

    @classmethod
    def get_scopes_from_request(cls, request):
        api_token = getattr(request, "api_token", None)
        if isinstance(api_token, ApiToken):
            return api_token.scopes

        return []
