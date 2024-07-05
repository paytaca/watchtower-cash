from rest_framework import permissions, exceptions

from paytacapos.models import Merchant

class HasMerchantObjectPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS: return True

        wallet = request.user
        if not wallet or not wallet.is_authenticated:
            return False

        if isinstance(obj, Merchant):
            return obj.wallet_hash == wallet.wallet_hash

        return obj.merchant.wallet_hash == wallet.wallet_hash
