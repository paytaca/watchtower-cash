from django.urls import re_path

from .views import *

urlpatterns = [
    re_path(r"^utxos/(?P<address>[\w+:]+)$", AddressUtxos.as_view(),name='cts-address-utxo'),
    re_path(r"^identity-outputs/(?P<authkey_owner_address>[\w+:]+)$", AuthKeyOwnerIdentityOutputs.as_view(),name='cts-authkey-owner-identity-output'),
    re_path(r"^identity-outputs/authguard/(?P<authguard_token_address>[\w+:]+)$", AuthGuardIdentityOutputs.as_view(),name='cts-authguard-identity-output'),
    re_path(r"^authchain-identities/(?P<authkey_owner_address>[\w+:]+)$", AuthchainIdentity.as_view(),name='cts-authchain-identity'),
    re_path(r"^authhead/$", Authhead.as_view(),name='cts-authchain-authhead'),
    re_path(r"^authkeys/(?P<authkey_owner_address>[\w+:]+)$", AuthKeys.as_view(),name='cts-authkey'),
    re_path(r"^balances/(?P<address>[\w+:]+)/fts$", FungibleTokenBalances.as_view(),name='cts-balance-fts')
]
