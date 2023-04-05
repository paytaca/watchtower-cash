from django.urls import path, re_path
from django.views.decorators.csrf import csrf_exempt
from rest_framework import routers
from main import views
from django.conf.urls import url

app_name = "main"


router = routers.DefaultRouter()
router.register(r"tokens", views.TokensViewSet, basename="tokens")
router.register(r"wallet/address-scan", views.WalletAddressScanViewSet, basename="address-scan")
router.register(r"wallet/preferences", views.WalletPreferencesViewSet, basename="wallet-preferences")
router.register(r"payment-requests", views.PaymentRequestViewSet, basename="payment-requests")

main_urls = router.urls

main_urls += [
    re_path(r"^task/(?P<task_id>[\w+:-]+)/$", views.TaskStatusView.as_view(), name='task-status'),

    re_path(r"^subscription/$", views.SubscribeViewSet.as_view(), name='subscribe'),

    re_path(r"^blockheight/latest/$", views.BlockHeightViewSet.as_view(), name='blockheight'),

    re_path(r"^balance/bch/(?P<bchaddress>[\w+:]+)/$", views.Balance.as_view(),name='bch-balance'),

    re_path(r"^balance/ct/(?P<tokenaddress>[\w+:]+)/$", views.Balance.as_view(),name='ct-balances'),
    re_path(r"^balance/ct/(?P<tokenaddress>[\w+:]+)/(?P<category>[\w+]+)/$", views.Balance.as_view(),name='ct-ft-balance'),
    re_path(r"^balance/ct/(?P<tokenaddress>[\w+:]+)/(?P<category>[\w+]+)/(?P<txid>[\w+]+)/(?P<index>[\w+]+)/$", views.Balance.as_view(),name='ct-nft-balance'),

    re_path(r"^balance/slp/(?P<slpaddress>[\w+:]+)/$", views.Balance.as_view(),name='slp-token-balances'),
    re_path(r"^balance/slp/(?P<slpaddress>[\w+:]+)/(?P<tokenid>[\w+]+)/$", views.Balance.as_view(),name='slp-token-balance'),
    re_path(r"^balance/wallet/(?P<wallethash>[\w+:]+)/$", views.Balance.as_view(),name='wallet-balance'),
    re_path(r"^balance/wallet/(?P<wallethash>[\w+:]+)/(?P<tokenid_or_category>[\w+]+)/$", views.Balance.as_view(),name='wallet-balance-ft-token'),
    re_path(r"^balance/wallet/(?P<wallethash>[\w+:]+)/(?P<category>[\w+]+)/(?P<txid>[\w+]+)/(?P<index>[\w+]+)/$", views.Balance.as_view(),name='wallet-balance-ct-nft-token'),
    re_path(r"^balance/spendable/bch/(?P<bchaddress>[\w+:]+)/$", views.SpendableBalance.as_view(),name='bch-spendable'),
    re_path(r"^balance/spendable/wallet/(?P<wallethash>[\w+:]+)/$", views.SpendableBalance.as_view(),name='wallet-spendable'),

    re_path(r"^utxo/bch/(?P<bchaddress>[\w+:]+)/$", views.UTXO.as_view(),name='bch-utxo'),
    re_path(r"^utxo/ct/(?P<tokenaddress>[\w+:]+)/$", views.UTXO.as_view(),name='ct-utxos'),
    re_path(r"^utxo/ct/(?P<tokenaddress>[\w+:]+)/(?P<category>[\w+]+)/$", views.UTXO.as_view(),name='ct-utxo'),
    re_path(r"^utxo/slp/(?P<slpaddress>[\w+:]+)/$", views.UTXO.as_view(),name='slp-utxo'),
    re_path(r"^utxo/slp/(?P<slpaddress>[\w+:]+)/(?P<tokenid>[\w+]+)/$", views.UTXO.as_view(),name='slp-token-utxo'),
    re_path(r"^utxo/wallet/(?P<wallethash>[\w+:]+)/scan/$", views.ScanUtxos.as_view(),name='scan-utxos'),
    re_path(r"^utxo/wallet/(?P<wallethash>[\w+:]+)/$", views.UTXO.as_view(),name='wallet-utxo'),
    re_path(r"^utxo/wallet/(?P<wallethash>[\w+:]+)/(?P<tokenid_or_category>[\w+]+)/$", views.UTXO.as_view(),name='wallet-utxo-token'),

    re_path(r"^history/wallet/(?P<wallethash>[\w+:]+)/$", views.WalletHistoryView.as_view(),name='wallet-history'),
    re_path(r"^history/wallet/(?P<wallethash>[\w+:]+)/(?P<tokenid>[\w+]+)/$", views.WalletHistoryView.as_view(),name='wallet-history-token'),
    
    re_path(r"^last-address-index/wallet/(?P<wallethash>[\w+:]+)/$", views.LastAddressIndexView.as_view(),name='wallet-last-address-index'),

    re_path(r"^tokens/wallet/(?P<wallethash>[\w+:]+)/$", views.WalletTokensView.as_view(),name='wallet-tokens'),

    re_path(r"^transactions/attributes/$", views.TransactionMetaAttributeView.as_view(),name='transaction-attributes'),

    # re_path(r"^tokens/(?P<tokenid>[\w+:]+)/$", views.TokensView.as_view(),name='tokens'),
    path('broadcast/', views.BroadcastViewSet.as_view(), name="broadcast-transaction")
]

test_urls = [
    re_path(r"^(?P<address>[\w+:]+)/$", views.TestSocket.as_view(),name='testbch'),
    re_path(r"^(?P<address>[\w+:]+)/(?P<tokenid>[\w+]+)", views.TestSocket.as_view(),name='testbch'),
]
