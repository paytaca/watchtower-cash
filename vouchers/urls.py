from rest_framework import routers

from .views import VoucherViewSet

router = routers.DefaultRouter()
router.register("vouchers", VoucherViewSet)

urlpatterns = router.urls
