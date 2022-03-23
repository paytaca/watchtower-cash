from rest_framework import routers

from smartbch.views import (
    TransactionTransferViewSet,
    TransactionViewSet,
)

router = routers.DefaultRouter()
router.register(r"transactions/transfers", TransactionTransferViewSet, basename="sbch-transaction-transfers")
router.register(r"transactions", TransactionViewSet, basename="sbch-transaction")

urlpatterns = router.urls + [
]
