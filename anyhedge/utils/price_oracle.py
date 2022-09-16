from ..js.runner import AnyhedgeFunctions

def get_price_messages(
    oracle_pubkey,
    relay:str=None,
    port:str=None,
    max_message_timestamp=None, 
    min_message_timestamp=None,
    count=None,
):
    """
        Fetches price messages from js script
        there might be more params in AnyhedgeFunctions.getPriceMessages that is not captured in this function
    """
    config = { "oraclePubKey": oracle_pubkey }
    requestParams = {}

    if relay is not None:
        config["oracleRelay"] = relay
    if port is not None:
        config["oraclePort"] = port

    if max_message_timestamp is not None:
        requestParams["maxMessageTimestamp"] = max_message_timestamp
    if min_message_timestamp is not None:
        requestParams["minMessageTimestamp"] = min_message_timestamp
    if count is not None:
        requestParams["count"] = count

    response = AnyhedgeFunctions.getPriceMessages(config, requestParams)
    if not response["success"]:
        error = "Error fetching price messages"
        if "error" in response:
            error += f". {response['error']}"
        raise Exception(error)

    return response["results"]


def parse_oracle_message(message, pubkey=None, signature=None):
    return AnyhedgeFunctions.parseOracleMessage(message, pubkey, signature)
