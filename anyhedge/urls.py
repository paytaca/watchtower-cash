from rest_framework import routers

from .views import (
    LongAccountViewSet,
    HedgePositionViewSet,
    HedgePositionOfferViewSet,
)

router = routers.DefaultRouter()
router.register(r"long-accounts", LongAccountViewSet, basename="hedge-long-accounts")
router.register(r"hedge-positions", HedgePositionViewSet, basename="hedge-positions")
router.register(r"hedge-position-offers", HedgePositionOfferViewSet, basename="hedge-position-offers")

urlpatterns = router.urls + [
]
