from rest_framework import routers

from .views import VaultViewSet

router = routers.DefaultRouter()
router.register("vaults", VaultViewSet, basename="vaults")

urlpatterns = router.urls
