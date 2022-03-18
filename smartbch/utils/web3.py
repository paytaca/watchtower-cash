import web3

from smartbch.conf import settings as app_settings

def create_web3_client():
    provider = web3.providers.rpc.HTTPProvider(app_settings.JSON_RPC_PROVIDER_URL)
    w3 = web3.Web3(provider)
    return w3
