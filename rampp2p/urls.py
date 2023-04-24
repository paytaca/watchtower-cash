from django.urls import path

from .views.ad import (
  AdListCreate,
#   AdList,
  AdDetail
)

from .views.payment import (
  PaymentTypeList,
  PaymentTypeDetail,
  PaymentMethodListCreate,
  PaymentMethodDetail
)

from .views.peer import (
  PeerListCreate,
  PeerDetail,
)

from .views.currency import (
  FiatCurrencyList,
  FiatCurrencyDetail,
  CryptoCurrencyList,
  CryptoCurrencyDetail
)

from .views.order import (
  OrderList,
  OrderDetail,
  OrderStatusList,
  ConfirmOrder,
  CryptoBuyerConfirmPayment,
  CryptoSellerConfirmPayment,
  ReleaseCrypto,
  RefundCrypto,
  CancelOrder
)

from .views.appeal import (
    AppealCancel,
    AppealRefund,
    AppealRelease,
)

from .views.feedback import (
  ArbiterFeedbackListCreate,
  PeerFeedbackListCreate,
  FeedbackDetail,
)

urlpatterns = [
  path('ad/', AdListCreate.as_view(), name='ad-list-create'),
  path('ad/<int:pk>', AdDetail.as_view(), name='ad-detail'),
  path('payment-type/', PaymentTypeList.as_view(), name='payment-type-list-create'),
  path('payment-type/<int:pk>', PaymentTypeDetail.as_view(), name='payment-type-detail'),
  path('payment-method/', PaymentMethodListCreate.as_view(), name='payment-method-list'),
  path('payment-method/<int:pk>', PaymentMethodDetail.as_view(), name='payment-method-detail'),
  path('peer/', PeerListCreate.as_view(), name='peer-list-create'),
  path('peer/<int:pk>', PeerDetail.as_view(), name='peer-detail'),
  path('currency/fiat/', FiatCurrencyList.as_view(), name='fiat-list-create'),
  path('currency/fiat/<int:pk>', FiatCurrencyDetail.as_view(), name='fiat-detail'),
  path('currency/crypto/', CryptoCurrencyList.as_view(), name='crypto-list-create'),
  path('currency/crypto/<int:pk>', CryptoCurrencyDetail.as_view(), name='crypto-detail'),

  path('order/', OrderList.as_view(), name='order-list-create'),
  path('order/<int:pk>', OrderDetail.as_view(), name='order-detail'),
  path('order/<int:pk>/status', OrderStatusList.as_view(), name='order-status-list'),
  path('order/<int:pk>/confirm', ConfirmOrder.as_view(), name='confirm-order'),
  path('order/<int:pk>/confirm-payment/buyer', CryptoBuyerConfirmPayment.as_view(), name='buyer-confirm-payment'),
  path('order/<int:pk>/confirm-payment/seller', CryptoSellerConfirmPayment.as_view(), name='seller-confirm-payment'),
  path('order/<int:pk>/release', ReleaseCrypto.as_view(), name='release-order'),
  path('order/<int:pk>/refund', RefundCrypto.as_view(), name='refund-order'),
  path('order/<int:pk>/cancel', CancelOrder.as_view(), name='cancel-order'),

  
  path('feedback/arbiter', ArbiterFeedbackListCreate.as_view(), name='arbiter-feedback-list-create'),
  path('feedback/<int:feedback_id>', FeedbackDetail.as_view(), name='feedback-detail'),
  path('feedback/peer', PeerFeedbackListCreate.as_view(), name='peer-feedback-list-create'),

  path('order/appeal/<int:pk>/cancel', AppealCancel.as_view(), name='appeal-cancel'),
  path('order/appeal/<int:pk>/release', AppealRelease.as_view(), name='appeal-release'),
  path('order/appeal/<int:pk>/refund', AppealRefund.as_view(), name='appeal-refund'),
]