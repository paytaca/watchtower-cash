from django.urls import path
from rest_framework import routers
from .views import PubkeyRegisterView, PubkeyUnregisterView, PubkeyCheckView

router = routers.DefaultRouter()

urlpatterns = router.urls + [
    path("register/", PubkeyRegisterView.as_view(), name='nostr-register'),
    path("unregister/", PubkeyUnregisterView.as_view(), name='nostr-unregister'),
    path("check/<str:pubkey_hex>/", PubkeyCheckView.as_view(), name='nostr-check'),
]
