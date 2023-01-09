from rest_framework import routers

from .views import (
    HedgePositionViewSet,
    HedgePositionOfferViewSet,

    OracleViewSet,
    PriceOracleMessageViewSet,
)

router = routers.DefaultRouter()
router.register(r"hedge-positions", HedgePositionViewSet, basename="hedge-positions")
router.register(r"hedge-position-offers", HedgePositionOfferViewSet, basename="hedge-position-offers")
router.register(r"oracles", OracleViewSet, basename="oracles")
router.register(r"price-messages", PriceOracleMessageViewSet, basename="price-messages")

urlpatterns = router.urls + [
]
