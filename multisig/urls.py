from django.urls import path
from .views import (
  MultisigWalletDeleteAPIView,
  MultisigWalletListCreateView,
  RenameMultisigWalletView,
  MultisigWalletDetailView,
  MultisigTransactionProposalListCreateView,
  MultisigTransactionProposalDetailView,
  SignatureAddView
)

urlpatterns = [
    path('wallets/', MultisigWalletListCreateView.as_view(), name='wallet-list-create'),
    path('wallets/<str:identifier>/', MultisigWalletDetailView.as_view(), name='wallet_detail') ,
    path('wallets/<int:pk>/rename/', RenameMultisigWalletView.as_view(), name='wallet-rename'),
    path('wallets/<int:pk>/delete/', MultisigWalletDeleteAPIView.as_view(), name='wallet-delete'),
    path('wallets/<int:wallet_pk>/transaction-proposals/', MultisigTransactionProposalListCreateView.as_view(), name='transaction-proposal-list-create'),
    path('wallets/<int:wallet_pk>/transaction-proposals/<int:proposal_id>/', MultisigTransactionProposalDetailView.as_view(), name='transaction-proposal-detail'),
    path('wallets/<int:wallet_pk>/transaction-proposals/<int:proposal_id>/signatures/<int:signer_id>', SignatureAddView.as_view(), name='transaction-proposal-signature-add'),
]
