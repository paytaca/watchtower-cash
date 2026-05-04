from django.urls import path
from rest_framework import routers
from .views import PushRegisterView, PushUnregisterView, PushCheckView

router = routers.DefaultRouter()

urlpatterns = router.urls + [
    path("push/register/", PushRegisterView.as_view(), name='nostr-push-register'),
    path("push/unregister/", PushUnregisterView.as_view(), name='nostr-push-unregister'),
    path("push/check/<str:pubkey_hex>/", PushCheckView.as_view(), name='nostr-push-check'),
]
