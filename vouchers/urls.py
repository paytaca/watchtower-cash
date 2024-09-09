from rest_framework import routers

from .views import *

router = routers.DefaultRouter()
router.register("", VoucherViewSet)
router.register("verification-token-minter", VerificationTokenMinterViewSet)
router.register("device-vaults", PosDeviceVaultViewSet)

urlpatterns = router.urls
