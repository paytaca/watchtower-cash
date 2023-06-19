from django.urls import path

from rampp2p.views import *

urlpatterns = [
    path('ad/', AdListCreate.as_view(), name='ad-list-create'),
    path('ad/<int:pk>', AdDetail.as_view(), name='ad-detail'),

    path('payment-type/', PaymentTypeList.as_view(), name='payment-type-list'),
    path('payment-type/<int:pk>', PaymentTypeDetail.as_view(), name='payment-type-detail'),

    path('payment-method/', PaymentMethodListCreate.as_view(), name='payment-method-list'),
    path('payment-method/<int:pk>', PaymentMethodDetail.as_view(), name='payment-method-detail'),

    path('peer/', PeerListCreate.as_view(), name='peer-list-create'),
    path('peer/<int:pk>', PeerDetail.as_view(), name='peer-detail'),

    path('currency/fiat/', FiatCurrencyList.as_view(), name='fiat-list'),
    path('currency/fiat/<int:pk>', FiatCurrencyDetail.as_view(), name='fiat-detail'),
    path('currency/crypto/', CryptoCurrencyList.as_view(), name='crypto-list'),
    path('currency/crypto/<int:pk>', CryptoCurrencyDetail.as_view(), name='crypto-detail'),

    path('order/', OrderListCreate.as_view(), name='order-list-create'),
    path('order/<int:pk>', OrderDetail.as_view(), name='order-detail'),
    path('order/<int:pk>/status', OrderListStatus.as_view(), name='order-list-status'),
    path('order/<int:pk>/generate-contract', CreateContract.as_view(), name='generate-contract'),
    path('order/<int:pk>/confirm', ConfirmOrder.as_view(), name='confirm-order'),
    path('order/<int:pk>/escrow-confirm', EscrowConfirmOrder.as_view(), name='escrow-confirm-order'),
    path('order/<int:pk>/confirm-payment/buyer', CryptoBuyerConfirmPayment.as_view(), name='buyer-confirm-payment'),
    path('order/<int:pk>/confirm-payment/seller', CryptoSellerConfirmPayment.as_view(), name='seller-confirm-payment'),
    path('order/<int:pk>/mark-release', MarkForRelease.as_view(), name='mark-release'),
    path('order/<int:pk>/validate-release', ValidateRelease.as_view(), name='validate-release'),
    path('order/<int:pk>/mark-refund', MarkForRefund.as_view(), name='mark-refund'),
    path('order/<int:pk>/validate-refund', ValidateRefund.as_view(), name='validate-refund'),
    path('order/appeal/<int:pk>/release', AppealRelease.as_view(), name='appeal-release'),
    path('order/appeal/<int:pk>/refund', AppealRefund.as_view(), name='appeal-refund'),

    path('feedback/arbiter', ArbiterFeedbackListCreate.as_view(), name='arbiter-feedback-list-create'),
    path('feedback/<int:feedback_id>', FeedbackDetail.as_view(), name='feedback-detail'),
    path('feedback/peer', PeerFeedbackListCreate.as_view(), name='peer-feedback-list-create'),

    path('order/contract/', ContractList.as_view(), name='contract-list'),
    path('order/contract/<int:pk>', ContractDetail.as_view(), name='contract-detail'),
    
    path('utils/transaction-detail', TransactionDetail.as_view(), name='transaction-detail'),
    path('utils/verify-message', VerifyMessageView.as_view(), name='verify-message'),
    path('utils/subscribe-address', SubscribeAddress.as_view(), name='subscribe-address'),
    
]