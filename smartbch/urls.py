from rest_framework import routers

from smartbch.views import (
    TransactionTransferViewSet,
)

router = routers.DefaultRouter()
router.register(r"transactions/transfers", TransactionTransferViewSet, basename="sbch-transaction-transfers")

urlpatterns = router.urls + [
]
