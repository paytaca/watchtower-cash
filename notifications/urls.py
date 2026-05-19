from django.urls import re_path
from rest_framework import routers

from .views import (
    DeviceSubscriptionView,
    DeviceUnsubscribeView,
    DeviceStatusView,
    TestPushNotificationView,
)

router = routers.DefaultRouter()

urlpatterns = router.urls + [
    re_path(r"^subscribe/$", DeviceSubscriptionView.as_view(), name='device-subscription'),
    re_path(r"^unsubscribe/$", DeviceUnsubscribeView.as_view(), name='device-unsubscribe'),
    re_path(r"^devices/$", DeviceStatusView.as_view(), name='device-status'),
    re_path(r"^test-send/$", TestPushNotificationView.as_view(), name='test-push-notification'),
]
