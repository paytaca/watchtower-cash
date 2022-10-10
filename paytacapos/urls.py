from django.urls import path

from .views import (
    BroadcastPaymentView,
)

urlpatterns = [
    path('broadcast/', BroadcastPaymentView.as_view(), name="broadcast-pos-payment")
]
