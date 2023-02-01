import pytz
from datetime import datetime

from anyhedge.models import (
    HedgePositionOffer,
    HedgePositionOfferCounterParty,
    PriceOracleMessage,
)
from .factory import generate_random_contract

def parse_timestamp(data):
    return datetime.fromtimestamp(data).replace(tzinfo=pytz.UTC)

def new_random():
    random_contract = generate_random_contract()
    contract_data = random_contract["contract_data"]
    other = random_contract["other"]
    if contract_data["metadata"]["takerSide"] == "hedge":
        taker = other["hedge_keys"]
        maker = other["long_keys"]
    else:
        taker = other["long_keys"]
        maker = other["hedge_keys"]

    hedge_position_offer = HedgePositionOffer.objects.create(
        position=contract_data["metadata"]["takerSide"],
        wallet_hash=taker["wallet_hash"],
        satoshis=other["bch"] * 10 ** 8,
        duration_seconds=other["duration"],
        high_liquidation_multiplier=contract_data["metadata"]["highLiquidationPriceMultiplier"],
        low_liquidation_multiplier=contract_data["metadata"]["lowLiquidationPriceMultiplier"],
        oracle_pubkey=contract_data["parameters"]["oraclePublicKey"],
        address=taker["address"],
        pubkey=taker["pubkey"],
        address_path="0/0",
    )
    
    counter_party = HedgePositionOfferCounterParty.objects.update_or_create(
        hedge_position_offer = hedge_position_offer,
        defaults=dict(
            contract_address=contract_data["address"],
            anyhedge_contract_version=contract_data["version"],
            wallet_hash=maker["wallet_hash"],
            address=maker["address"],
            pubkey=maker["pubkey"],
            address_path="0/0",
            price_message_timestamp=parse_timestamp(contract_data["parameters"]["startTimestamp"]),
            price_value=contract_data["metadata"]["startPrice"],
            oracle_message_sequence=other["price"]["price_data"]["message_sequence"],
            starting_oracle_message=other["price"]["message"],
            starting_oracle_signature=other["price"]["signature"],
            settlement_deadline=parse_timestamp(contract_data["parameters"]["startTimestamp"] + 60 * 15),
            settlement_service_fee=0,
            settlement_service_fee_address="",
        )
    )

    price_oracle_message, _ = PriceOracleMessage.objects.get_or_create(
        pubkey=other["price"]["pubkey"],
        signature=other["price"]["signature"],
        message=other["price"]["message"],
        message_timestamp=parse_timestamp(other["price"]["price_data"]["message_timestamp"]),
        price_value=other["price"]["price_data"]["price"],
        price_sequence=other["price"]["price_data"]["price_sequence"],
        message_sequence=other["price"]["price_data"]["message_sequence"],
    )

    return hedge_position_offer, counter_party, price_oracle_message
