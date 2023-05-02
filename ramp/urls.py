from rest_framework import routers
from django.urls import re_path, path
from django.views.decorators.csrf import csrf_exempt

from .views import (
    RampWebhookView,
    RampShiftView,
    RampShiftHistoryView,
    RampShiftExpireView,
    # RampCreateShift
)

router = routers.DefaultRouter()

urlpatterns = router.urls + [
    re_path('webhooks', RampWebhookView.as_view(), name="ramp-webhook"),
    re_path('shift', RampShiftView.as_view(), name="ramp-shift"),    
    re_path(r'^history/(?P<wallet_hash>[\w+:]+)/$', RampShiftHistoryView.as_view(), name='shift-history'),
    re_path('expire', RampShiftExpireView.as_view(), name='shift-expire'),
    # path('create-shift', RampCreateShift.as_view(), name='create-shift')
    # re_path('history', RampShiftHistoryView.as_view(), name='shift-history')
]