from rest_framework import routers
from chat.views import ChatIdentityViewSet

router = routers.DefaultRouter()
router.register(r"identity", ChatIdentityViewSet, basename="chat-identity")

urlpatterns = router.urls + [
]
