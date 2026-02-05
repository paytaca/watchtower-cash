from django.urls import path
from multisig.views.coordinator import (
    ServerIdentityListCreateView,
    ServerIdentityDetailView,
)
from multisig.views.wallet import (
    MultisigWalletListCreateView,
    SignerWalletListView
)
from multisig.views.transaction import (
    ProposalListCreateView,
    ProposalDetailView,
    ProposalInputListView,
    ProposalSigningSubmissionListCreateView,
    ProposalSigningSubmissionDetailView,
)

urlpatterns = [
    path('wallets/', MultisigWalletListCreateView.as_view(), name='wallet-list-create'),
    path('coordinator/server-identities/', ServerIdentityListCreateView.as_view(), name='server-identity-list-create'),
    path('coordinator/server-identities/<str:public_key>/', ServerIdentityDetailView.as_view(), name='server-identity-detail'),
    path('signers/<str:public_key>/wallets/', SignerWalletListView.as_view(), name='signer-wallet-list'),
    path('proposals/', ProposalListCreateView.as_view(), name='proposal-list-create'),
    path('proposals/<int:pk>/', ProposalDetailView.as_view(), name='proposal-detail'),
    path('proposals/<int:proposal_pk>/inputs/', ProposalInputListView.as_view(), name='proposal-input-list'),
    path('proposals/<int:proposal_pk>/signing-submissions/', ProposalSigningSubmissionListCreateView.as_view(), name='proposal-signing-submission-list-create'),
    path('proposals/<int:proposal_pk>/signing-submissions/<int:pk>/', ProposalSigningSubmissionDetailView.as_view(), name='proposal-signing-submission-detail'),
]

