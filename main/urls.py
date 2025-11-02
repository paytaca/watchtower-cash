from django.urls import path, re_path
from rest_framework import routers
from main import views

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

app_name = "main"


router = routers.DefaultRouter()

router.register(r"", views.BcmrWebhookViewSet, basename="webhook")
router.register(r"tokens", views.TokensViewSet, basename="tokens")
router.register(r"cashtokens/fungible", views.CashFungibleTokensViewSet, basename="cashtokens-ft")
router.register(r"cashtokens/nft", views.CashNftsViewSet, basename="cashtokens-nft")
router.register(r"wallet/address-scan", views.WalletAddressScanViewSet, basename="address-scan")
router.register(r"wallet/preferences", views.WalletPreferencesViewSet, basename="wallet-preferences")
router.register(r"payment-requests", views.PaymentRequestViewSet, basename="payment-requests")
router.register(r"wallet/shard", views.WalletShardViewSet, basename="wallet-shard")
router.register(r"app-control", views.AppControlViewSet, basename="app-control")
router.register(r"transactions/outputs", views.TransactionOutputViewSet, basename="transaction-outputs")
router.register(r"projects", views.ProjectViewSet, basename="projects")

main_urls = router.urls


main_urls += [
    re_path(r"^market-prices/$", views.LatestMarketPriceView.as_view(),name='latest-market-price'),
    re_path(r"^bch-prices/$", views.LatestBCHPriceView.as_view(),name='latest-bch-price'),
    re_path(r"^asset-prices/$", views.UnifiedAssetPriceView.as_view(),name='unified-asset-prices'),
    re_path(r"^price-chart/(?P<relative_currency>[\w+:-]+)/$", views.PriceChartView.as_view(),name='price-chart'),
    re_path(r"^status/$", views.StatusView.as_view(), name='api-status'),
    re_path(r"^task/(?P<task_id>[\w+:-]+)/$", views.TaskStatusView.as_view(), name='task-status'),

    re_path(r"^subscription/$", views.SubscribeViewSet.as_view(), name='subscribe'),

    re_path(r"^blockheight/latest/$", views.BlockHeightViewSet.as_view(), name='blockheight'),

    re_path(r"^blockchain/info/$", views.BlockChainView.as_view(), name='blockchain-info'),

    re_path(r"^live-updates/payment/$", views.LiveUpdatesPaymentView.as_view(), name='live-updates-payment'),

    re_path(r"^projects/leaderboard/(?P<project_id>[\w+:-]+)/$", views.ProjectLeaderboardView.as_view(), name='project-leaderboard'),
    re_path(r"^projects/wallets/(?P<project_id>[\w+:-]+)/$", views.ProjectWalletsView.as_view(), name='project-wallets'),

    re_path(r"^address-info/bch/(?P<bchaddress>[\w+:]+)/$", views.AddressInfoView.as_view(),name='bch-address-info'),
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

    re_path(r"^history/contract/(?P<address>[\w+:]+)/$", views.ContractHistoryView.as_view(),name='contract-history'),
    re_path(r"^history/wallet/(?P<wallethash>[\w+:]+)/$", views.WalletHistoryView.as_view(),name='wallet-history'),
    re_path(r"^history/wallet/(?P<wallethash>[\w+:]+)/(?P<tokenid_or_category>[\w+]+)/$", views.WalletHistoryView.as_view(),name='wallet-history-ft-token'),
    re_path(r"^history/wallet/(?P<wallethash>[\w+:]+)/(?P<category>[\w+]+)/(?P<txid>[\w+]+)/(?P<index>[\w+]+)/$", views.WalletHistoryView.as_view(),name='wallet-history-ct-nft-token'),
    re_path(r"^history-rebuild/wallet/(?P<wallethash>[\w+:]+)/$", views.RebuildHistoryView.as_view(),name='rebuild-wallet-history'),

    re_path(r"^last-address-index/wallet/(?P<wallethash>[\w+:]+)/$", views.LastAddressIndexView.as_view(),name='wallet-last-address-index'),

    re_path(r"^tokens/wallet/(?P<wallethash>[\w+:]+)/$", views.WalletTokensView.as_view(),name='wallet-tokens'),

    re_path(r"^transactions/attributes/$", views.TransactionMetaAttributeView.as_view(),name='transaction-attributes'),
    re_path(r"^transactions/(?P<txid>[\w+]+)/$", views.TransactionDetailsView.as_view(),name='transaction-details'),

    re_path(r"^wallet-addresses/(?P<wallethash>[\w+:]+)/$", views.WalletAddressesView.as_view(),name='wallet-addresses'),
    re_path(r"^wallet-address-paths/(?P<wallethash>[\w+:]+)/$", views.WalletAddressPathsView.as_view(),name='wallet-address-paths'),

    # re_path(r"^tokens/(?P<tokenid>[\w+:]+)/$", views.TokensView.as_view(),name='tokens'),
    path('transaction/spender/', views.SpenderTransactionView.as_view(), name='find-transaction-spender'),
    path('broadcast/', views.BroadcastViewSet.as_view(), name="broadcast-transaction"),

    path('wallet/shard/get/', views.WalletShardViewSet.as_view({'get': 'get_first_shard'}), name='wallet-shard-get-shard'),
    
    # App version
    path('version/check/<str:platform>/', views.check_app_version),
    path('nonce/', views.NonceAPIView.as_view()),
    path('wallet-address-app/', views.WalletAddressAppView.as_view()),
    path('wallet-address-app-record-exists/', views.WalletAddressAppRecordExistsView.as_view()),

    # Asset Setting
    path('app-setting/custom-list/', views.AssetOrderingView.as_view(), name="asset-ordering"),
    path('app-setting/favorites/', views.AssetFavoritesView.as_view(), name="asset-favorites"),
    path('app-setting/unlisted-list/', views.AssetUnlistedView.as_view(), name="asset-unlisted"),
    re_path('app-setting/register/', views.RegisterView.as_view(), name="register-user"),
    re_path('app-setting/auth/', TokenObtainPairView.as_view(), name="memo-auth" ),
    re_path('app-setting/refresh/', TokenRefreshView.as_view(), name="refresh-auth"),

]

test_urls = [
    re_path(r"^(?P<address>[\w+:]+)/$", views.TestSocket.as_view(),name='testbch'),
    re_path(r"^(?P<address>[\w+:]+)/(?P<tokenid>[\w+]+)", views.TestSocket.as_view(),name='testbch'),
]
