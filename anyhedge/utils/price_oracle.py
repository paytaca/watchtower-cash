import pytz
from datetime import datetime
from ..models import PriceOracleMessage
from ..js.runner import AnyhedgeFunctions


def save_price_oracle_message(oracle_pubkey, price_message):
    price_oracle_message, created = PriceOracleMessage.objects.update_or_create(
        pubkey = oracle_pubkey,
        signature = price_message["priceMessage"]["signature"],
        message = price_message["priceMessage"]["message"],
        defaults={
            "message_timestamp": datetime.fromtimestamp(price_message["priceData"]["messageTimestamp"]).replace(tzinfo=pytz.UTC),
            "price_value": price_message["priceData"]["priceValue"],
            "price_sequence": price_message["priceData"]["priceSequence"],
            "message_sequence": price_message["priceData"]["messageSequence"],
        }
    )
    return price_oracle_message


def get_price_messages(
    oracle_pubkey,
    relay:str=None,
    port:str=None,
    max_message_timestamp=None, 
    min_message_timestamp=None,
    max_message_sequence=None,
    min_message_sequence=None,
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
    if min_message_sequence is not None:
        requestParams["minMessageSequence"] = min_message_sequence
    if max_message_sequence is not None:
        requestParams["maxMessageSequence"] = max_message_sequence
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
