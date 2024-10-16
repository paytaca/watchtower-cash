from django.urls import path
from rampp2p.views import *

urlpatterns = [
    
    path('version/check/<str:platform>/', check_app_version),
    
    path('ad/', AdView.as_view(), name='ad-list-create'),
    path('ad/<int:pk>/', AdView.as_view(), name='ad-detail'),
    path('ad/snapshot/', AdSnapshotView.as_view(), name='ad-snapshot'),
    path('ad/cash-in/', CashInAdViewSet.as_view({'get': 'list'})),

    path('cash-in/presets/', CashInAdViewSet.as_view({'get': 'list_presets'})),
    path('cash-in/ad/payment-types/', CashInAdViewSet.as_view({'get': 'retrieve_ad_count_by_payment_types'})),
    path('cash-in/ad/', CashInAdViewSet.as_view({'get': 'retrieve_ads_by_presets'})),
    path('cash-in/order/', CashinOrderViewSet.as_view({'get': 'list'}), name='cashin-order-list'),
    path('cash-in/order/alerts/', CashinOrderViewSet.as_view({'get': 'check_alerts'}), name='cashin-order-alerts'),

    path('user/', UserProfileView.as_view(), name='user-profile'),
    path('peer/', PeerView.as_view(), name='peer-create-edit'),
    path('peer/<int:pk>/', PeerView.as_view(), name='peer-detail'),
    path('arbiter/', ArbiterView.as_view(), name='arbiter-list-create-edit'),
    path('arbiter/<str:wallet_hash>/', ArbiterView.as_view(), name='arbiter-detail'),

    path('currency/fiat/', FiatCurrencyViewSet.as_view({'get': 'list'}), name='fiat-list'),
    path('currency/fiat/<int:pk>/', FiatCurrencyViewSet.as_view({'get': 'retrieve'}), name='fiat-detail'),
    path('currency/crypto/', CryptoCurrencyViewSet.as_view({'get': 'list'}), name='crypto-list'),
    path('currency/crypto/<int:pk>/', CryptoCurrencyViewSet.as_view({'get': 'retrieve'}), name='crypto-detail'),

    # Orders
    path('order/', OrderViewSet.as_view({'get': 'list', 'post': 'create'}), name='order-list-create'),
    path('order/<int:pk>/', OrderViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update'}), name='order-detail-edit'),
    path('order/<int:pk>/members/', OrderViewSet.as_view({'get': 'members', 'patch': 'members'}), name='order-members'),
    path('order/<int:pk>/status/', OrderStatusViewSet.as_view({'get': 'list_status', 'patch': 'read_status'}), name='order-list-edit-status'),
    path('order/<int:pk>/cancel/', OrderStatusViewSet.as_view({'post': 'cancel'}), name='order-cancel'),
    path('order/<int:pk>/confirm/', OrderStatusViewSet.as_view({'post': 'confirm'}), name='order-confirm'),
    path('order/<int:pk>/pending-escrow/', OrderStatusViewSet.as_view({'post': 'pending_escrow'}), name='order-pending-escrow'),
    path('order/<int:pk>/confirm-payment/buyer/', OrderStatusViewSet.as_view({'post': 'buyer_confirm_payment'}), name='buyer-confirm-payment'),
    path('order/<int:pk>/confirm-payment/seller/', OrderStatusViewSet.as_view({'post': 'seller_confirm_payment'}), name='seller-confirm-payment'),

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

    path('utils/market-price/', MarketRates.as_view(), name='market-price'),
    path('utils/subscribe-address/', SubscribeContractAddress.as_view(), name='subscribe-address'),
    
    path('chats/webhook/', ChatWebhookView.as_view(), name='chat-webhook'),

    # Old endpoints kept for backward-compatibility
    path('cashin/ad', CashInAdsList.as_view()),
    path('ad/<int:pk>', AdDetail.as_view()),
    path('ad-snapshot', AdSnapshotView.as_view()),
    path('payment-method/<int:pk>', PaymentMethodDetail.as_view()),
    path('peer/create', PeerCreateView.as_view()),
    path('peer/detail', PeerDetailView.as_view()),
    path('user', UserProfileView.as_view()),
    path('arbiter/detail', ArbiterDetail.as_view()),
    path('currency/fiat/<int:pk>', FiatCurrencyDetail.as_view()),
    path('currency/crypto/<int:pk>', CryptoCurrencyDetail.as_view()),
    path('cashin/order', CashinOrderList.as_view()),
    path('order/<int:pk>', OrderDetail.as_view()),
    path('order/<int:pk>/members', OrderMemberView.as_view()),
    path('order/<int:pk>/status', OrderListStatus.as_view()),
    path('order/<int:pk>/cancel', CancelOrder.as_view()),
    path('order/<int:pk>/confirm', ConfirmOrder.as_view()),
    path('order/<int:pk>/pending-escrow', PendingEscrowOrder.as_view()),
    path('order/<int:pk>/confirm-payment/buyer', CryptoBuyerConfirmPayment.as_view()),
    path('order/<int:pk>/confirm-payment/seller', CryptoSellerConfirmPayment.as_view()),
    path('order/payment/attachment/upload', UploadOrderPaymentAttachmentView.as_view()),
    path('order/payment/attachment/delete', DeleteOrderPaymentAttachmentView.as_view()),
    path('order/<int:pk>/verify-escrow', VerifyEscrow.as_view()),
    path('order/<int:pk>/verify-release', VerifyRelease.as_view()),
    path('order/<int:pk>/verify-refund', VerifyRefund.as_view()),
    path('appeal', AppealList.as_view()),
    path('order/<int:pk>/appeal', AppealRequest.as_view()),
    path('order/<int:pk>/appeal/pending-release', AppealPendingRelease.as_view()),
    path('order/<int:pk>/appeal/pending-refund', AppealPendingRefund.as_view()),
    path('order/feedback/arbiter', ArbiterFeedbackListCreate.as_view()),
    path('order/feedback/peer', PeerFeedbackListCreate.as_view()),
    path('order/feedback/<int:feedback_id>', FeedbackDetail.as_view()),
    path('order/contract/create', ContractCreateView.as_view()),
    path('order/contract', ContractDetailsView.as_view()),
    path('order/contract/transactions', ContractTransactionsView.as_view()),
    path('order/contract/fees', ContractFeesView.as_view()),
    path('utils/market-price', MarketRates.as_view()),
    path('utils/subscribe-address', SubscribeContractAddress.as_view()),
]