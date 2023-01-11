from rest_framework import routers
from chat.views import PgpInfoViewSet

router = routers.DefaultRouter()
router.register(r"info", PgpInfoViewSet, basename="chat-pgp-info")

urlpatterns = router.urls + [
]
