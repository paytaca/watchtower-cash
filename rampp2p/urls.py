from django.urls import path

from .views.ad import (
  AdListCreate,
  AdDetail
)

from .views.payment import (
  PaymentTypeListCreate,
  PaymentTypeDetail,
  PaymentMethodListCreate,
  PaymentMethodDetail
)

from .views.peer import (
  PeerListCreate,
  PeerDetail
)

urlpatterns = [
  path('ad/', AdListCreate.as_view(), name='ad-list'),
  path('ad/<int:pk>/', AdDetail.as_view(), name='ad-detail'),
  path('payment-type/', PaymentTypeListCreate.as_view(), name='payment-type-list'),
  path('payment-type/<int:pk>', PaymentTypeDetail.as_view(), name='payment-type-detail'),
  path('payment-method/', PaymentMethodListCreate.as_view(), name='payment-method-list'),
  # path('payment-method/create', PaymentMethodCreate.as_view(), name='payment-method-create'),
  path('payment-method/<int:pk>', PaymentMethodDetail.as_view(), name='payment-method-detail'),
  path('peer/', PeerListCreate.as_view(), name='peer-list'),
  path('peer/<int:pk>', PeerDetail.as_view(), name='peer-detail')
]