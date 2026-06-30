from django.urls import path
from rest_framework import routers
from .views import (
    PubkeyRegisterView,
    PubkeyUnregisterView,
    PubkeyCheckView,
    PubkeyLastOnlineView,
    PubkeyTouchView,
    ShowActiveStatusView,
)

router = routers.DefaultRouter()

urlpatterns = router.urls + [
    path("register/", PubkeyRegisterView.as_view(), name='nostr-register'),
    path("unregister/", PubkeyUnregisterView.as_view(), name='nostr-unregister'),
    path("check/<str:pubkey_hex>/", PubkeyCheckView.as_view(), name='nostr-check'),
    path("last-active/", PubkeyLastOnlineView.as_view(), name='nostr-last-active'),
    path("touch/", PubkeyTouchView.as_view(), name='nostr-touch'),
    path("active-status/", ShowActiveStatusView.as_view(), name='nostr-active-status'),
]
