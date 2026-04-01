from .wallet import (
    MultisigWalletListCreateView,
    # MultisigWalletDetailView,
    # RenameMultisigWalletView,
    # MultisigWalletUtxosView
)

from .transaction import (
    ProposalListCreateView,
    ProposalDetailView,
    ProposalInputListView,
)

__all__ = [
    "MultisigWalletListCreateView",
    "ProposalListCreateView",
    "ProposalDetailView",
    "ProposalInputListView"
]
