from django.urls import path
from .views import (
    MultisigWalletListCreateView,
    MultisigWalletDetailView,
    MultisigWalletTransactionListView,
    SignerListCreateView,
    SignerDetailView,
    SignerTransactionListView,
    TransactionListCreateView,
    TransactionDetailView,
    TransactionSignaturesListView,
    SignatureListCreateView,
    SignatureDetailView
)

urlpatterns = [
    path('wallets/', MultisigWalletListCreateView.as_view()),
    path('wallets/<int:pk>/', MultisigWalletDetailView.as_view()),
    path('wallets/<int:wallet_id>/transactions/', MultisigWalletTransactionListView.as_view(), name='wallet-transactions'),

    path('signers/', SignerListCreateView.as_view()),
    path('signers/<int:pk>/', SignerDetailView.as_view()),
    path('signers/<int:signer_id>/transactions/', SignerTransactionListView.as_view(), name='signer-transactions'),

    path('transactions/', TransactionListCreateView.as_view()),
    path('transactions/<int:pk>/', TransactionDetailView.as_view()),
    path('transactions/<int:transaction_id>/signatures/', TransactionSignaturesListView.as_view(), name='transaction-signatures'),

    path('signatures/', SignatureListCreateView.as_view()),
    path('signatures/<int:pk>/', SignatureDetailView.as_view()),
]
