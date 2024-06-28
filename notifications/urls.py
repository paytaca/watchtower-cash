from django.urls import re_path
from rest_framework import routers

from .views import (
    DeviceSubscriptionView,
    DeviceUnsubscribeView,
)

router = routers.DefaultRouter()

urlpatterns = router.urls + [
    re_path(r"^subscribe/$", DeviceSubscriptionView.as_view(), name='device-subscription'),
    re_path(r"^unsubscribe/$", DeviceUnsubscribeView.as_view(), name='device-unsubscribe'),
]
