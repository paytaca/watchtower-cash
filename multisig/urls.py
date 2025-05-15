from django.urls import path
from .views.wallet import (
  MultisigWalletDeleteAPIView,
  MultisigWalletListCreateView,
  RenameMultisigWalletView,
  MultisigWalletDetailView
)

urlpatterns = [
    path('wallets/', MultisigWalletListCreateView.as_view(), name='wallet-list-create'),
    path('wallets/<int:pk>/', MultisigWalletDetailView.as_view(), name='wallet_detail'),
    path('wallets/<int:pk>/rename/', RenameMultisigWalletView.as_view(), name='wallet-rename'),
    path('wallets/<int:pk>/delete/', MultisigWalletDeleteAPIView.as_view(), name='wallet-delete'),

]


