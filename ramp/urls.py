from rest_framework import routers
from django.urls import re_path
from .views import (
    RampWebhookView
)

router = routers.DefaultRouter()

urlpatterns = router.urls + [
    re_path('webhooks', RampWebhookView.as_view(), name="ramp-webhook")
]