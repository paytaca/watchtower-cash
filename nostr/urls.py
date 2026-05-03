from django.urls import re_path
from rest_framework import routers
from .views import PushRegisterView, PushUnregisterView

router = routers.DefaultRouter()

urlpatterns = router.urls + [
    re_path(r"^push/register/$", PushRegisterView.as_view(), name='nostr-push-register'),
    re_path(r"^push/unregister/$", PushUnregisterView.as_view(), name='nostr-push-unregister'),
]
