from rest_framework import routers

from smartbch.views import (
    TokenContractViewSet,
    TransactionTransferViewSet,
    TransactionViewSet,
)

router = routers.DefaultRouter()
router.register(r"token-contracts", TokenContractViewSet, basename="sbch-token-contracts")
router.register(r"transactions/transfers", TransactionTransferViewSet, basename="sbch-transaction-transfers")
router.register(r"transactions", TransactionViewSet, basename="sbch-transaction")

urlpatterns = router.urls + [
]
