from django.urls import re_path
from rest_framework import routers

from .views import (
    InvoiceBitPayView,
    InvoiceProtobufView,
    InvoiceViewSet,
)

router = routers.DefaultRouter()
router.register(r"invoices", InvoiceViewSet, basename="invoices")

urlpatterns = router.urls + [
    re_path(r"^i/(?P<uuid>[\w+:-]+)/$", InvoiceProtobufView.as_view(), name='invoice-protobuf'),   
    re_path(r"^i/bitpay/(?P<uuid>[\w+:-]+)/$", InvoiceBitPayView.as_view(), name='invoice-bitpay'),   
]
