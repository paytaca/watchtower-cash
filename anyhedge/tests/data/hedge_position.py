import json
import pytz
from datetime import datetime

from anyhedge.models import (
    HedgePosition,
    HedgePositionMetadata,
    PriceOracleMessage,
)
from .factory import (
    generate_random_contract,
    fetch_saved_test_data,
)

def parse_timestamp(data):
    return datetime.fromtimestamp(data).replace(tzinfo=pytz.UTC)

def load_test_data():
    test_data = fetch_saved_test_data()
    return save_data_to_models(test_data)

def new_random():
    random_contract = generate_random_contract()
    return save_data_to_models(random_contract)

def save_data_to_models(test_data):
    contract_data = test_data["contract_data"]
    other = test_data["other"]

    hedge_position = HedgePosition.objects.create(        
        address=contract_data["address"],
        anyhedge_contract_version=contract_data["version"],
        satoshis=contract_data["metadata"]["hedgeInputInSatoshis"],
        start_timestamp=parse_timestamp(contract_data["parameters"]["startTimestamp"]),
        maturity_timestamp=parse_timestamp(contract_data["parameters"]["maturityTimestamp"]),
        hedge_wallet_hash=other["hedge_keys"]["wallet_hash"],
        hedge_address=contract_data["metadata"]["hedgePayoutAddress"],
        hedge_pubkey=contract_data["parameters"]["hedgeMutualRedeemPublicKey"],
        hedge_address_path=None,
        long_wallet_hash=other["long_keys"]["wallet_hash"],
        long_address=contract_data["metadata"]["longPayoutAddress"],
        long_pubkey=contract_data["parameters"]["longMutualRedeemPublicKey"],
        long_address_path=None,
        oracle_pubkey=contract_data["parameters"]["oraclePublicKey"],
        start_price=contract_data["metadata"]["startPrice"],
        low_liquidation_multiplier=contract_data["metadata"]["lowLiquidationPriceMultiplier"],
        high_liquidation_multiplier=contract_data["metadata"]["highLiquidationPriceMultiplier"],

        starting_oracle_message=contract_data["metadata"]["startingOracleMessage"],
        starting_oracle_signature=contract_data["metadata"]["startingOracleSignature"],
        funding_tx_hash=None,
        funding_tx_hash_validated=False,
    )

    metadata, _ = HedgePositionMetadata.objects.update_or_create(
        hedge_position=hedge_position,
        defaults=dict(
            position_taker=contract_data["metadata"]["takerSide"],
            liquidity_fee=None,
            network_fee=None,
            total_hedge_funding_sats=None,
            total_long_funding_sats=None,
        ),
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

    return hedge_position, metadata, price_oracle_message
