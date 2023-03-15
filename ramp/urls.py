from rest_framework import routers
from django.urls import re_path
from .views import (
    RampWebhookView,
    RampShiftView
)

router = routers.DefaultRouter()

urlpatterns = router.urls + [
    re_path('webhooks', RampWebhookView.as_view(), name="ramp-webhook"),
    re_path('shift', RampShiftView.as_view(), name="ramp-shift")
]