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

from .views.currency import (
  FiatListCreateView,
  FiatDetailView,
  CryptoListCreateView,
  CryptoDetailView
)

from .views.order import (
  OrderListCreate,
  OrderDetail,
  OrderStatusList
)

from .views.feedback import (
  ArbiterFeedbackListCreate,
  FeedbackDetail
)

urlpatterns = [
  path('ad/', AdListCreate.as_view(), name='ad-list'),
  path('ad/<int:pk>/', AdDetail.as_view(), name='ad-detail'),
  path('payment-type/', PaymentTypeListCreate.as_view(), name='payment-type-list'),
  path('payment-type/<int:pk>', PaymentTypeDetail.as_view(), name='payment-type-detail'),
  path('payment-method/', PaymentMethodListCreate.as_view(), name='payment-method-list'),
  path('payment-method/<int:pk>', PaymentMethodDetail.as_view(), name='payment-method-detail'),
  path('peer/', PeerListCreate.as_view(), name='peer-list'),
  path('peer/<int:pk>', PeerDetail.as_view(), name='peer-detail'),
  path('currency/fiat/', FiatListCreateView.as_view(), name='fiat-list-create'),
  path('currency/fiat/<int:pk>', FiatDetailView.as_view(), name='fiat-detail'),
  path('currency/crypto/', CryptoListCreateView.as_view(), name='crypto-list-create'),
  path('currency/crypto/<int:pk>', CryptoDetailView.as_view(), name='crypto-detail'),
  path('order/', OrderListCreate.as_view(), name='order-list-create'),
  path('order/<int:pk>', OrderDetail.as_view(), name='order-detail'),
  path('order/<int:pk>/status', OrderStatusList.as_view(), name='order-status-list'),
  path('feedback/arbiter', ArbiterFeedbackListCreate.as_view(), name='arbiter-feedback-list-create'),
  path('feedback/<int:feedback_id>', FeedbackDetail.as_view(), name='feedback-detail'),
]