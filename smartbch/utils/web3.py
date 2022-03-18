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
