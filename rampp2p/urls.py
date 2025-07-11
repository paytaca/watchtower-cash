from django.urls import path, re_path
from rampp2p.views import *
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'order/public', PublicOrdersViewSet, basename='public-orders')


urlpatterns = [
    *router.urls,
    path('version/check/<str:platform>/', check_app_version),
    
    path('ad/', AdViewSet.as_view({'get': 'list', 'post': 'create'})),
    path('ad/<int:pk>/', AdViewSet.as_view({'get': 'retrieve', 'put': 'partial_update', 'delete': 'destroy'})),
    path('ad/check/limit/', AdViewSet.as_view({'get': 'check_ad_limit'})),
    path('ad/currency/', AdViewSet.as_view({'get': 'retrieve_currencies'})),
    path('ad/snapshot/<int:pk>/', AdSnapshotViewSet.as_view({'get': 'retrieve'})),
    path('ad/cash-in/', CashInAdViewSet.as_view({'get': 'list'})),
    re_path(r'^ad/share/$', AdShareLinkView.as_view(), name='adview'),

    path('cash-in/presets/', CashInAdViewSet.as_view({'get': 'list_presets'})),
    path('cash-in/ad/payment-types/', CashInAdViewSet.as_view({'get': 'retrieve_ad_count_by_payment_types'})),
    path('cash-in/ad/', CashInAdViewSet.as_view({'get': 'retrieve_ads_by_presets'})),
    path('cash-in/order/', CashinOrderViewSet.as_view({'get': 'list'}), name='cashin-order-list'),
    path('cash-in/order/alerts/', CashinOrderViewSet.as_view({'get': 'check_alerts'}), name='cashin-order-alerts'),

    path('user/', UserAuthView.as_view(), name='user-profile'),
    path('peer/', PeerViewSet.as_view({ 'get': 'retrieve_by_user', 'post': 'create', 'patch': 'partial_update' })),
    path('peer/<int:pk>/', PeerViewSet.as_view({ 'get': 'retrieve'})),
    path('peer/<str:wallet_hash>/', PeerViewSet.as_view({ 'get': 'retrieve_by_wallet'})),
    path('arbiter/', ArbiterView.as_view(), name='arbiter-list-create-edit'),
    path('arbiter/<str:wallet_hash>/', ArbiterView.as_view(), name='arbiter-detail'),

    path('currency/fiat/', FiatCurrencyViewSet.as_view({'get': 'list'}), name='fiat-list'),
    path('currency/fiat/<int:pk>/', FiatCurrencyViewSet.as_view({'get': 'retrieve'}), name='fiat-detail'),
    path('currency/crypto/', CryptoCurrencyViewSet.as_view({'get': 'list'}), name='crypto-list'),
    path('currency/crypto/<int:pk>/', CryptoCurrencyViewSet.as_view({'get': 'retrieve'}), name='crypto-detail'),

    # Orders
    # path('order/public/', PublicOrdersViewSet.as_view({'get': 'list'}), name='public-order-list-retrieve'),
    # path('order/public/<int:pk>/', PublicOrdersViewSet.as_view({'get': 'retrieve'}), name='public-order-detail'),
    path('order/', OrderViewSet.as_view({'get': 'list', 'post': 'create'}), name='order-list-create'),
    path('order/<int:pk>/', OrderViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update'}), name='order-detail-edit'),
    path('order/<int:pk>/ad/snapshot/', AdSnapshotViewSet.as_view({'get': 'retrieve_by_order'})),
    path('order/<int:pk>/members/', OrderViewSet.as_view({'get': 'members', 'patch': 'members'}), name='order-members'),
    path('order/<int:pk>/status/', OrderStatusViewSet.as_view({'get': 'list_status', 'patch': 'read_status'}), name='order-list-edit-status'),
    path('order/<int:pk>/cancel/', OrderStatusViewSet.as_view({'post': 'cancel'}), name='order-cancel'),
    path('order/<int:pk>/confirm/', OrderStatusViewSet.as_view({'post': 'confirm'}), name='order-confirm'),
    path('order/<int:pk>/pending-escrow/', OrderStatusViewSet.as_view({'post': 'pending_escrow'}), name='order-pending-escrow'),
    path('order/<int:pk>/confirm-payment/buyer/', OrderStatusViewSet.as_view({'post': 'buyer_confirm_payment'}), name='buyer-confirm-payment'),
    path('order/<int:pk>/confirm-payment/seller/', OrderStatusViewSet.as_view({'post': 'seller_confirm_payment'}), name='seller-confirm-payment'),

    # Contract
    path('order/<int:pk>/contract/', ContractViewSet.as_view({'get': 'retrieve_by_order'}), name='order-contract-detail'),
    path('order/<int:pk>/contract/fees/', ContractViewSet.as_view({'get': 'contract_fees'}), name='order-contract-fees'),
    path('order/<int:pk>/contract/transactions/', ContractViewSet.as_view({'get': 'transactions_by_order'}), name='order-contract-tx'),
    path('order/<int:pk>/verify-escrow/', ContractViewSet.as_view({'post': 'verify_escrow'}), name='verify-escrow'),
    path('order/<int:pk>/verify-release/', ContractViewSet.as_view({'post': 'verify_release'}), name='verify-release'),
    path('order/<int:pk>/verify-refund/', ContractViewSet.as_view({'post': 'verify_refund'}), name='verify-refund'),
    path('order/contract/', ContractViewSet.as_view({'post': 'create'}), name='contract-create'),
    path('order/contract/<int:pk>/', ContractViewSet.as_view({'get': 'retrieve'}), name='contract-detail'),
    path('order/contract/<int:pk>/transactions/', ContractViewSet.as_view({'get': 'transactions'}), name='contract-tx'),
    path('contract/fees/', ContractViewSet.as_view({'get': 'fees'}), name='contract-fees'),
    
    path('order/cash-in/', CashinOrderViewSet.as_view({'get': 'list'}), name='cashin-order-list'),
    path('order/cash-in/alerts/', CashinOrderViewSet.as_view({'get': 'check_alerts'}), name='cashin-order-alerts'),
    path('order/status/', OrderStatusViewSet.as_view({'patch': 'read_order_status'})),
    
    # Payment
    path('order/payment/', OrderPaymentViewSet.as_view({'get': 'list'}), name='order-payment-list'),
    path('order/payment/<int:pk>/', OrderPaymentViewSet.as_view({'get': 'retrieve'}), name='order-payment-detail'),
    path('order/payment/<int:pk>/attachment/', OrderPaymentViewSet.as_view({'post': 'upload_attachment', 'delete': 'delete_attachment'}), name='payment-attachment-upload-delete'),
    path('payment-type/', PaymentTypeView.as_view(), name='payment-type-list'),
    path('payment-method/', PaymentMethodViewSet.as_view({'get': 'list', 'post': 'create'}), name='payment-method-list'),
    path('payment-method/<int:pk>/', PaymentMethodViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), name='payment-method-detail'),

    # Appeal
    path('appeal/', AppealViewSet.as_view({'get': 'list', 'post': 'create'}), name='appeal-list-create'),
    path('appeal/<int:pk>/', AppealViewSet.as_view({'get': 'retrieve'}), name='appeal-detail'),
    path('appeal/<int:pk>/pending-release/', AppealViewSet.as_view({'post': 'pending_release'}), name='appeal-pending-release'),
    path('appeal/<int:pk>/pending-refund/', AppealViewSet.as_view({'post': 'pending_refund'}), name='appeal-pending-refund'),
    path('order/<int:pk>/appeal/', AppealViewSet.as_view({'get': 'retrieve_by_order'}), name='order-appeal-detail'),

    # Feedback
    path('order/feedback/arbiter/', ArbiterFeedbackViewSet.as_view({'get': 'list', 'post': 'create'}), name='arbiter-feedback-list-create'),
    path('order/feedback/peer/', PeerFeedbackViewSet.as_view({'get': 'list', 'post': 'create'}), name='peer-feedback-list-create'),

    # Utils
    path('utils/calculate-fees/', ContractFeeCalculation.as_view()),
    path('utils/market-price/', MarketPrices.as_view(), name='market-price'),
    path('utils/subscribe-address/', SubscribeContractAddress.as_view(), name='subscribe-address'),
    path('chats/webhook/', ChatWebhookView.as_view(), name='chat-webhook'),
    path('feature-toggles/', check_feature_control),
    path('feature-control/', check_feature_control)
]