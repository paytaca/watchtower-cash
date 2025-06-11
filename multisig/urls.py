from django.urls import path
from .views import (
  MultisigWalletListCreateView,
  RenameMultisigWalletView,
  MultisigWalletDetailView,
  MultisigTransactionProposalListCreateView,
  MultisigTransactionProposalDetailView,
  SignerSignaturesAddView,
  SignaturesAddView
)

urlpatterns = [
    path('wallets/', MultisigWalletListCreateView.as_view(), name='wallet-list-create'),
    path('wallets/<str:identifier>/', MultisigWalletDetailView.as_view(), name='wallet_detail') ,
    path('wallets/<int:pk>/rename/', RenameMultisigWalletView.as_view(), name='wallet-rename'),
    path('wallets/<str:wallet_identifier>/transaction-proposals/', MultisigTransactionProposalListCreateView.as_view(), name='transaction-proposal-list-create'),
    path('transaction-proposals/<str:proposal_identifier>/', MultisigTransactionProposalDetailView.as_view(), name='transaction-proposal-detail'),
    path('transaction-proposals/<str:proposal_identifier>/signatures/', SignaturesAddView.as_view(), name='transaction-proposal-signatures-add'),
    path('transaction-proposals/<str:proposal_identifier>/signatures/<str:signer_identifier>', SignerSignaturesAddView.as_view(), name='transaction-proposal-signer-signatures-add')
]
