from django.urls import path

from rampp2p.views import *

urlpatterns = [
    path('ad/', AdListCreate.as_view(), name='ad-list-create'),
    path('ad/<int:pk>', AdDetail.as_view(), name='ad-detail'),
    path('ad-snapshot', AdSnapshotView.as_view(), name='ad-snapshot'),

    path('payment-type/', PaymentTypeList.as_view(), name='payment-type-list'),
    path('payment-method/', PaymentMethodListCreate.as_view(), name='payment-method-list'),
    path('payment-method/<int:pk>', PaymentMethodDetail.as_view(), name='payment-method-detail'),

    path('peer/create', PeerCreateView.as_view(), name='peer-create'),
    path('peer/detail', PeerDetailView.as_view(), name='peer-detail'),
    path('user', UserProfileView.as_view(), name='user-profile'),
    path('arbiter/', ArbiterListCreate.as_view(), name='arbiter-list-create'),
    path('arbiter/detail', ArbiterDetail.as_view(), name='arbiter-detail'),
    path('arbiter/config', ArbiterConfig.as_view(), name='arbiter-config'),

    path('currency/fiat/', FiatCurrencyList.as_view(), name='fiat-list'),
    path('currency/fiat/<int:pk>', FiatCurrencyDetail.as_view(), name='fiat-detail'),
    path('currency/crypto/', CryptoCurrencyList.as_view(), name='crypto-list'),
    path('currency/crypto/<int:pk>', CryptoCurrencyDetail.as_view(), name='crypto-detail'),

    path('order/', OrderListCreate.as_view(), name='order-list-create'),
    path('order/<int:pk>', OrderDetail.as_view(), name='order-detail'),
    path('order/<int:pk>/members', OrderMembers.as_view(), name='order-members'),
    path('order/<int:pk>/status', OrderListStatus.as_view(), name='order-list-status'),
    path('order/<int:pk>/cancel', CancelOrder.as_view(), name='order-cancel'),
    path('order/<int:pk>/confirm', ConfirmOrder.as_view(), name='confirm-order'),
    path('order/<int:pk>/pending-escrow', PendingEscrowOrder.as_view(), name='pending-escrow'),
    path('order/<int:pk>/confirm-payment/buyer', CryptoBuyerConfirmPayment.as_view(), name='buyer-confirm-payment'),
    path('order/<int:pk>/confirm-payment/seller', CryptoSellerConfirmPayment.as_view(), name='seller-confirm-payment'),
    
    path('order/<int:pk>/verify-escrow', VerifyEscrow.as_view(), name='verify-escrow'),
    path('order/<int:pk>/verify-release', VerifyRelease.as_view(), name='verify-release'),
    path('order/<int:pk>/verify-refund', VerifyRefund.as_view(), name='verify-refund'),

    path('appeal', AppealList.as_view(), name='appeal-list'),
    path('order/<int:pk>/appeal', AppealRequest.as_view(), name='appeal-request'),
    path('order/<int:pk>/appeal/pending-release', AppealPendingRelease.as_view(), name='appeal-pending-release'),
    path('order/<int:pk>/appeal/pending-refund', AppealPendingRefund.as_view(), name='appeal-pending-refund'),

    path('order/feedback/arbiter', ArbiterFeedbackListCreate.as_view(), name='arbiter-feedback-list-create'),
    path('order/feedback/peer', PeerFeedbackListCreate.as_view(), name='peer-feedback-list-create'),
    path('order/feedback/<int:feedback_id>', FeedbackDetail.as_view(), name='feedback-detail'),

    path('order/contract/create', ContractCreateView.as_view(), name='generate-contract'),
    path('order/contract', ContractDetailsView.as_view(), name='contract-detail'),
    path('order/contract/transactions', ContractTransactionsView.as_view(), name='contract-transactions'),
    path('order/contract/fees', ContractFeesView.as_view(), name='contract-fees'),
    
    path('utils/market-price', MarketRates.as_view(), name='market-price'),
    path('utils/subscribe-address', SubscribeContractAddress.as_view(), name='subscribe-address'),
    
    path('chats/webhook/', ChatWebhookView.as_view(), name='chat-webhook')
]