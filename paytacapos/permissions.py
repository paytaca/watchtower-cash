import logging
from rest_framework import permissions, exceptions

from paytacapos.models import Merchant, PaymentMethod

LOGGER = logging.getLogger("django")

class HasPaymentObjectPermission(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS: return True

        wallet = request.user
        if not wallet or not wallet.is_authenticated:
            return False

        if not isinstance(obj, PaymentMethod):
            return False
        
        return obj.owner.wallet_hash == wallet.wallet_hash

class HasMerchantObjectPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):
        LOGGER.exception("CHECKING MERCHANT OBJECT PERMISSION")
        if request.method in permissions.SAFE_METHODS: return True

        wallet = request.user
        if not wallet or not wallet.is_authenticated:
            return False

        if isinstance(obj, Merchant):
            return obj.wallet_hash == wallet.wallet_hash

        return obj.merchant.wallet_hash == wallet.wallet_hash

class HasMinPaytacaVersionHeader(permissions.BasePermission):
    """
        - Use with other permissions ex:
            permission_classes = [
                HasMinPaytacaVersionHeader | HasMerchantObjectPermission
            ]
        - Only checks for object permissions & write apis
    """
    # any version greater than this will reject 
    ALLOW_MAX_VERSION = "0.19.1" # inclusive

    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS: return True

        paytaca_app_version = request.headers.get('X_PAYTACA_APP_VERSION', '')
        if not self.is_valid_version(paytaca_app_version):
            return True

        if self.compare_versions(self.ALLOW_MAX_VERSION, paytaca_app_version) == False:
            return True

        return False

    @classmethod
    def on_request(cls, request):
        return cls().has_object_permission(request, None, None)

    @classmethod
    def is_valid_version(cls, value:str):
        try:
            if not isinstance(value, str):
                return False

            tokens = value.split(".", 2)
            tokens = [int(token) for token in tokens]

            if len(tokens) != 3:
                return False

            return True
        except (TypeError, ValueError, AttributeError):
            return False

    @classmethod
    def compare_versions(cls, v1:str, v2:str):
        """
            Returns:
                - True if v1 is greater than v2
                - False if v1 is less than v2
                - None if equal
        """
        v1_tokens = v1.split(".", 2)
        v1_tokens = [int(token) for token in v1_tokens]

        v2_tokens = v2.split(".", 2)
        v2_tokens = [int(token) for token in v2_tokens]

        for index in range(len(v1_tokens)):
            v1_token = v1_tokens[index]
            v2_token = v2_tokens[index]
            if v1_token > v2_token:
                return True
            elif v1_token < v2_token:
                return False

        return None
