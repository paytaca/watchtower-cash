from django.urls import path
from rampp2p.views import *

urlpatterns = [
    path('ad/', AdView.as_view(), name='ad-list-create'),
    path('ad/<int:pk>/', AdView.as_view(), name='ad-detail'),
    path('ad/snapshot/', AdSnapshotView.as_view(), name='ad-snapshot'),
    path('ad/cash-in/', CashInAdView.as_view(), name='cashin-ads-list'),

    path('payment-type/', PaymentTypeList.as_view(), name='payment-type-list'),
    path('payment-method/', PaymentMethodListCreate.as_view(), name='payment-method-list'),
    path('payment-method/<int:pk>', PaymentMethodDetail.as_view(), name='payment-method-detail'),

    path('user/', UserProfileView.as_view(), name='user-profile'),
    path('peer/', PeerView.as_view(), name='peer-create-edit'),
    path('peer/<int:pk>/', PeerView.as_view(), name='peer-detail'),
    path('arbiter/', ArbiterView.as_view(), name='arbiter-list-create-edit'),
    path('arbiter/<str:wallet_hash>/', ArbiterView.as_view(), name='arbiter-detail'),

    path('currency/fiat/', FiatCurrencyList.as_view(), name='fiat-list'),
    path('currency/fiat/<int:pk>', FiatCurrencyDetail.as_view(), name='fiat-detail'),
    path('currency/crypto/', CryptoCurrencyList.as_view(), name='crypto-list'),
    path('currency/crypto/<int:pk>', CryptoCurrencyDetail.as_view(), name='crypto-detail'),

    # Orders
    path('order/', OrderViewSet.as_view({'get': 'list', 'post': 'create'}), name='order-list-create'),
    path('order/<int:pk>/', OrderViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update'}), name='order-detail-edit'),
    path('order/<int:pk>/members/', OrderViewSet.as_view({'get': 'members', 'patch': 'members'}), name='order-members'),
    path('order/<int:pk>/status/', OrderViewSet.as_view({'get': 'list_status'}), name='order-list-status'),
    path('order/<int:pk>/cancel/', OrderViewSet.as_view({'post': 'cancel'}), name='order-cancel'),
    path('order/<int:pk>/confirm/', OrderViewSet.as_view({'post': 'confirm'}), name='order-confirm'),
    path('order/<int:pk>/pending-escrow/', OrderViewSet.as_view({'post': 'pending_escrow'}), name='order-pending-escrow'),
    path('order/<int:pk>/confirm-payment/buyer/', OrderViewSet.as_view({'post': 'buyer_confirm_payment'}), name='buyer-confirm-payment'),
    path('order/<int:pk>/confirm-payment/seller/', OrderViewSet.as_view({'post': 'seller_confirm_payment'}), name='seller-confirm-payment'),

    # Contract
    path('order/<int:pk>/contract/', ContractViewSet.as_view({'get': 'retrieve_by_order'}), name='order-contract-detail'),
    path('order/<int:pk>/contract/transactions/', ContractViewSet.as_view({'get': 'transactions_by_order'}), name='order-contract-tx'),
    path('order/<int:pk>/verify-escrow/', ContractViewSet.as_view({'post': 'verify_escrow'}), name='verify-escrow'),
    path('order/<int:pk>/verify-release/', ContractViewSet.as_view({'post': 'verify_release'}), name='verify-release'),
    path('order/<int:pk>/verify-refund/', ContractViewSet.as_view({'post': 'verify_refund'}), name='verify-refund'),
    path('order/contract/', ContractViewSet.as_view({'post': 'create'}), name='contract-create'),
    path('order/contract/<int:pk>/', ContractViewSet.as_view({'get': 'retrieve'}), name='contract-detail'),
    path('order/contract/<int:pk>/transactions/', ContractViewSet.as_view({'get': 'transactions'}), name='contract-tx'),
    path('order/contract/fees/', ContractViewSet.as_view({'get': 'fees'}), name='contract-fees'),
    
    path('order/cash-in/', CashinOrderView.as_view(), name='cashin-order-list'),
    path('order/payment/attachment/upload', UploadOrderPaymentAttachmentView.as_view(), name='upload-payment-attachment'),
    path('order/payment/attachment/delete', DeleteOrderPaymentAttachmentView.as_view(), name='delete-payment-attachment'),

    # Appeal
    path('appeal/', AppealViewSet.as_view({'get': 'list', 'post': 'create'}), name='appeal-list-create'),
    path('appeal/<int:pk>/', AppealViewSet.as_view({'get': 'retrieve'}), name='appeal-detail'),
    path('appeal/<int:pk>/pending-release/', AppealViewSet.as_view({'post': 'pending_release'}), name='appeal-pending-release'),
    path('appeal/<int:pk>/pending-refund/', AppealViewSet.as_view({'post': 'pending_refund'}), name='appeal-pending-refund'),
    path('order/<int:pk>/appeal/', AppealViewSet.as_view({'get': 'retrieve_by_order'}), name='order-appeal-detail'),

    # Feedback
    path('order/feedback/arbiter/', ArbiterFeedbackViewSet.as_view({'get': 'list', 'post': 'create'}), name='arbiter-feedback-list-create'),
    path('order/feedback/peer/', PeerFeedbackViewSet.as_view({'get': 'list', 'post': 'create'}), name='peer-feedback-list-create'),

    path('utils/market-price', MarketRates.as_view(), name='market-price'),
    path('utils/subscribe-address', SubscribeContractAddress.as_view(), name='subscribe-address'),
    
    path('chats/webhook/', ChatWebhookView.as_view(), name='chat-webhook'),
]