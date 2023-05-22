# import bitcoincash.rpc
# from bitcoincash.core import lx
# from bitcoincash.wallet import CBitcoinAddress

import logging
logger = logging.getLogger(__name__)

def verify_transaction(txid):
    # rpc = bitcoincash.rpc.Proxy()
    # tx = rpc.getrawtransaction(lx(txid))
    # logger.warning(f'tx.vout: {tx.vout}')
    
    # outputs = []
    # for o in tx.vout:
    #     address = str(CBitcoinAddress.from_scriptPubKey(o.scriptPubKey))
    #     outputs.append(address)

    # logger.warning(f'outputs: {outputs}')
    return "outputs"