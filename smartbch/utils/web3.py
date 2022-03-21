import re
import web3

from smartbch.conf import settings as app_settings

from .formatters import (
    format_block_number,
    pad_hex_string,
)


def create_web3_client():
    provider = web3.providers.rpc.HTTPProvider(app_settings.JSON_RPC_PROVIDER_URL)
    w3 = web3.Web3(
        provider,
        external_modules={
            "sbch": SmartBCHModule,
        }
    )
    return w3


# munger is needed for methods that use params, check web3.method.Method docs
# mungers preprocess args and kwargs passed in a Method call before they are passed as param to the JSON-RPC request
# ideally define specific mungers for specific rpc methods
def unsafe_munger(module, *args):
    return args


class SmartBCHModule(web3.module.Module):
    # For more details, see RPC docs
    # https://docs.smartbch.org/smartbch/developers-guide/jsonrpc#sbch

    """
        Returns:
            txs: list of transactions, the class type of some properties differ from web3's:
            AttributeDict({
                'blockHash': '0x6a6509625946f46727be6df14f9e1731666260fe4931040114266e9aa4cf4ae6',
                'blockNumber': '0x8af41',
                'from': '0xd56e9af0243ffbbe4c6a801ad8f20a097d247122',
                'gas': '0x65b6',
                'gasPrice': '0x3e95ba80',
                'hash': '0x106afbfde9e02f8cd21d8b29568a43a753460d019b4a672822c129281524369f',
                'input': '0x',
                'nonce': '0x78c',
                'to': '0xda34ad1848424cca7e0ff55c7ef6c6fe46833456',
                'transactionIndex': '0x0',
                'value': '0x1c6bf52634000',
                'v': '0x43',
                'r': '0xe6ea923b481d48c5c181c6311b38a115bd73cd300cb167e15c34f5d0cca1fc6d',
                's': '0x14221e625532f8d705eea31654f0076a92744d679181497babd86000ff96885'
            })
    """
    query_tx_by_addr = web3.method.Method(
        web3.types.RPCEndpoint("sbch_queryTxByAddr"),
        mungers=[unsafe_munger],
    )

    query_logs = web3.method.Method(
        web3.types.RPCEndpoint("sbch_queryLogs"),
        mungers=[unsafe_munger],
    )

    eth_getLogs = web3.method.Method(
        web3.types.RPCEndpoint("eth_getLogs"),
        mungers=[unsafe_munger]
    )


    def query_transfer_events(
        self,
        wallet_address=None,
        contract_address=None,
        from_block='0x0',
        to_block='latest',
    ):
        """
        Returns:
            logs: list of transaction logs, example of log:
            AttributeDict({
                'address': '0x265bD28d79400D55a1665707Fa14A72978FA6043',
                'topics': [
                    HexBytes('0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'),
                    HexBytes('0x000000000000000000000000fea305d5fe76cf6ea4a887234264a256ad269792'),
                    HexBytes('0x000000000000000000000000659f04f36e90143fcac202d4bc36c699c078fc98')
                ],
                'data': '0x0000000000000000000000000000000000000000000000000000000000009c40',
                'blockNumber': 3632684,
                'transactionHash': HexBytes('0xfaf08a4f2e8c9e7a456a663976becec744c4b94a92387433822451e2519ba943'),
                'transactionIndex': 0,
                'blockHash': HexBytes('0x0853659d93da82f7fd3687efa9ba752cf3280ab4442e9b872e7090e84a6fa47a'),
                'logIndex': 0,
                'removed': False
            })
        """
        # Apparently, ERC20's & ERC721's `Transfer` event topic is the same hex string
        event_topic = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
        args = {
            "fromBlock": format_block_number(from_block),
            "toBlock": format_block_number(to_block),
            "topics": event_topic,
        }

        if wallet_address:
            if not web3.Web3.isAddress(wallet_address):
                raise ValueError(f"Expected 'wallet_address' to be a valid address, got: {wallet_address}")

            padded_address = pad_hex_string(wallet_address, target_length=64)
            # We can only do this since Transfer events of ERC20 and ERC721 token have the same indexed parameters
            args["topics"] = [
                [event_topic, padded_address],
                [event_topic, None, padded_address],
            ]

        if contract_address:
            if not web3.Web3.isAddress(contract_address):
                raise ValueError(f"Expected 'contract_address' to be a valid address, got: {contract_address}")
        else:
            contract_address = None

        return self.eth_getLogs(args)
