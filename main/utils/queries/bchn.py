from bitcoinrpc.authproxy import AuthServiceProxy

from django.conf import settings


class BCHN(object):

    def __init__(self):
        url = f"http://{settings.RPC_USER}:{settings.RPC_PASSWORD}@docker-host:8332"
        self.rpc_connection = AuthServiceProxy(url)
        self.source = f'bchn-{self.get_chain()}'
    
    def is_chipnet(self):
        return self.get_chain() == 'chip'

    def is_mainnet(self):
        return self.get_chain() == 'main'

    def get_chain(self):
        info = self.rpc_connection.getblockchaininfo()
        return info['chain']

    def get_latest_block(self):
        return self.rpc_connection.getblockcount()
        
    def get_block(self, block):
        block_hash = self.rpc_connection.getblockhash(block)
        block_data = self.rpc_connection.getblock(block_hash)
        return block_data['tx']

    def _get_raw_transaction(self, txid):
        return self.rpc_connection.getrawtransaction(txid, 2)
