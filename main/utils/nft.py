import json, base64, requests
from main.models import Token
from main.utils.queries.bchd import BCHDQuery
from django.conf import settings
import logging

LOGGER = logging.getLogger(__name__)


def bitdb_query(query):
    query_string = json.dumps(query)
    query_bytes = query_string.encode('ascii')
    query_b64 = base64.b64encode(query_bytes)
    url = f"https://bitdb.bch.sx/q/{query_b64.decode()}"
    return requests.get(url).json()


def find_token_utxo(tokenid):
    data = bitdb_query({
        "v": 3,
        "q": {
            "find": {
                "out.s3": "SEND",
                "out.h4": tokenid,
            },
            "project": {"tx.h": 1},
            "limit": 1
        }
    })

    txs = [*data["u"], *data["c"]]

    if len(txs):
        txid = txs[0]["tx"]["h"]
    else:
        # this implies the token, if exists, has not been sent
        # so we get the recipient when the token is minted
        txid = tokenid

    if getattr(settings, 'DISABLE_BCHD', True):
        LOGGER.warning("BCHD is disabled, cannot find token UTXO")
        return None

    bchd = BCHDQuery()
    tx = bchd._get_raw_transaction(txid)
    if not tx:
        return

    tx_output = None
    for output in tx.outputs:
        output_token_id = output.slp_token.token_id.hex()
        if output_token_id and output_token_id == tokenid:
            tx_output = dict(
                txid=tx.hash[::-1].hex(),
                index=output.index,
                address="simpleledger:" + output.slp_token.address,
            )
            break

    # check if utxo is burned
    if tx_output:
        data = bitdb_query({
            "v": 3,
            "q": {
                "find": {
                    "in.e.h": tx_output["txid"],
                    "in.e.i": tx_output["index"],
                },
                "project": {"tx.h": 1, "in.e.i": 1, "in.e.h": 1 },
                "limit": 1
            }
        })
        txs = [*data["u"], *data["c"]]
        if len(txs):
            for tx in txs:
                if "burning_txid" in tx_output:
                    break

                for tx_input in tx["in"]:
                    input_edge = tx_input["e"]
                    if input_edge["h"] == tx_output["txid"] and input_edge["i"] == tx_output["index"]:
                        tx_output["burning_txid"] = tx["tx"]["h"]
                        break


    return tx_output


def find_minting_baton(tokenid):
    data = bitdb_query({
        "v": 3,
        "q": {
            "find": {
                "$or": [
                    { "tx.h": tokenid, "out.s3": "GENESIS" },
                    { "out.h4": tokenid, "out.s3": "MINT" }
                ]
            },
        },
        "project": { "tx.h": 1 },
        "limit": 1,
    })

    # results are arranged in chronological order
    txs = [*data["u"], *data["c"]]
    txid = txs[0]["tx"]["h"] if len(txs) else None

    if not txid:
        return

    if getattr(settings, 'DISABLE_BCHD', True):
        LOGGER.warning("BCHD is disabled, cannot find minting baton")
        return None

    bchd = BCHDQuery()
    tx = bchd.get_transaction(txid, parse_slp=True)
    for tx_output in tx["outputs"]:
        if tx_output.get("is_mint_baton", False):
            return {
                "txid": tx["txid"],
                "index": tx_output["index"],
                "address": tx_output["address"],
            }
