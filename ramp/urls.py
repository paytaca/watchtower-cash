from rest_framework import routers
from django.urls import path

from .views import (
    RampWebhookView
)

router = routers.DefaultRouter()

urlpatterns = router.urls + [
     path('webhooks/', RampWebhookView.as_view(), name="ramp-webhook")
]