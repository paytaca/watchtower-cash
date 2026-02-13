from django.urls import path
from multisig.views.coordinator import (
    ServerIdentityListCreateView,
    ServerIdentityDetailView,
)
from multisig.views.wallet import (
    MultisigWalletDetailView,
    MultisigWalletListCreateView,
    SignerWalletListView
)
from multisig.views.transaction import (
    ProposalListCreateView,
    ProposalDetailView,
    ProposalStatusView,
    WalletProposalListView,
    ProposalInputListView,
    ProposalSigningSubmissionListCreateView,
    ProposalSigningSubmissionDetailView,
    ProposalSignatureListView,
    ProposalSignatureDetailView,
    SignatureBySignerIdentifierList,
)

urlpatterns = [
    path('wallets/', MultisigWalletListCreateView.as_view(), name='wallet-list-create'),
    path('wallets/<str:identifier>/', MultisigWalletDetailView.as_view(), name='wallet-detail'),
    path('wallets/<str:identifier>/proposals/', WalletProposalListView.as_view(), name='wallet-list-proposals'),
    path('coordinator/server-identities/', ServerIdentityListCreateView.as_view(), name='server-identity-list-create'),
    path('coordinator/server-identities/<str:public_key>/', ServerIdentityDetailView.as_view(), name='server-identity-detail'),
    path('signers/<str:public_key>/wallets/', SignerWalletListView.as_view(), name='signer-wallet-list'),
    path('proposals/', ProposalListCreateView.as_view(), name='proposal-list-create'),
    path('proposals/<str:identifier>/', ProposalDetailView.as_view(), name='proposal-detail'),
    path('proposals/<str:identifier>/status/', ProposalStatusView.as_view(), name='proposal-status'),
    path('proposals/<str:identifier>/inputs/', ProposalInputListView.as_view(), name='proposal-input-list'),
    path('proposals/<str:identifier>/signing-submissions/', ProposalSigningSubmissionListCreateView.as_view(), name='proposal-signing-submission-list-create'),
    path('proposals/<str:identifier>/signing-submissions/<int:pk>/', ProposalSigningSubmissionDetailView.as_view(), name='proposal-signing-submission-detail'),
    path('proposals/<str:identifier>/signatures/', ProposalSignatureListView.as_view(), name='proposal-signature-list'),
    path('proposals/<str:identifier>/signatures/<int:pk>/', ProposalSignatureDetailView.as_view(), name='proposal-signature-detail'),
    path('proposals/<str:proposal_identifier>/signatures/<str:identifier>/', SignatureBySignerIdentifierList.as_view(), name='signature-list-by-signature-identifier'),
]

