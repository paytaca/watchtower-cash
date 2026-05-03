from django.urls import path
from rest_framework import routers
from .views import PushRegisterView, PushUnregisterView

router = routers.DefaultRouter()

urlpatterns = router.urls + [
    path("push/register/", PushRegisterView.as_view(), name='nostr-push-register'),
    path("push/unregister/", PushUnregisterView.as_view(), name='nostr-push-unregister'),
]
