from datetime import datetime, timedelta
from ..js.runner import AnyhedgeFunctions
from ..models import (
    HedgePositionOffer,
    Oracle,
    PriceOracleMessage,
)


def calculate_hedge_sats(long_sats=0.0, low_price_mult=1, price_value=None):
    """
        Calculate hedge satoshis based on long satoshis
        NOTE: resulting value is off by some small amount due to the
            original formula (calculating long sats from hedge sats) uses unreversible function "round"
        More info on the equation in: https://gist.github.com/khirvy019/f5786918dddb63413c5cd412335a8354
    """
    if price_value:
        low_liquidation_price = round(price_value * low_price_mult)
        calculated_sats = round(long_sats / ((price_value / low_liquidation_price) - 1))
    else:
        # long_sats = (calculated_sats / low_price_mult) - calculated_sats
        # long_sats = calculated_sats * (1/low_price_mult - 1)
        # long_sats = calculated_sats * (1-low_price_mult)/low_price_mult
        # calculated_sats =  long_sats / (1-low_price_mult)/low_price_mult
        calculated_sats =  long_sats * low_price_mult / (1-low_price_mult)
    return calculated_sats


def create_contract(
    satoshis:int=0,
    low_price_multiplier:float=0.9,
    high_price_multiplier:float=2,
    duration_seconds:int=0,
    taker_side:str="",
    short_address:str="",
    short_pubkey:str="",
    long_address:str="",
    long_pubkey:str="",
    oracle_pubkey:str=None,
    price_oracle_message_sequence:int=None,
):
    intent =  {
        "amount": satoshis/10**8,
        "lowPriceMult": low_price_multiplier,
        "highPriceMult": high_price_multiplier,
        "duration": duration_seconds,
        "takerSide": taker_side,
    }
    pubkeys = {
        "shortAddress": short_address,
        "shortPubkey": short_pubkey,
        "longAddress": long_address,
        "longPubkey": long_pubkey,
    }

    priceMessageConfig = None
    if oracle_pubkey:
        oracle = Oracle.objects.filter(pubkey=oracle_pubkey).first()
        priceMessageConfig = {
            "oraclePubKey": oracle_pubkey,
        }
        if oracle:
            priceMessageConfig["oracleRelay"] = oracle.relay
            priceMessageConfig["oraclePort"] = oracle.port

    priceMessageRequestParams = None
    if price_oracle_message_sequence:
        priceMessageRequestParams = {
            "minMessageSequence": price_oracle_message_sequence,
            "maxMessageSequence": price_oracle_message_sequence,
        }

    startingPriceMessage = None
    if oracle_pubkey and price_oracle_message_sequence:
        price_oracle_message = PriceOracleMessage.objects.filter(
            pubkey=oracle_pubkey, message_sequence=price_oracle_message_sequence
        ).first()
        if price_oracle_message:
            startingPriceMessage = {
                "publicKey": price_oracle_message.pubkey,
                "message": price_oracle_message.message,
                "signature": price_oracle_message.signature,
            }

    return AnyhedgeFunctions.create(intent, pubkeys, startingPriceMessage, priceMessageConfig, priceMessageRequestParams)

def compile_contract(
    takerSide:str="",
    nominal_units:int=0,
    oraclePublicKey:str="",
    startingOracleMessage:str="",
    startingOracleSignature:str="",
    maturityTimestamp:int=0,
    highLiquidationPriceMultiplier:float=0.0,
    lowLiquidationPriceMultiplier:float=0.0,
    shortPublicKey:str="",
    longPublicKey:str="",
    shortAddress:str="",
    longAddress:str="",
    fees:list=[],
    fundings:list=[],
    contract_version:str="",
):
    data = {
        "takerSide": takerSide,
        "makerSide": "long" if takerSide == "short" else "short",
        "nominalUnits": nominal_units,
        "oraclePublicKey": oraclePublicKey,
        "startingOracleMessage": startingOracleMessage,
        "startingOracleSignature": startingOracleSignature,
        "maturityTimestamp": maturityTimestamp,
        "highLiquidationPriceMultiplier": highLiquidationPriceMultiplier,
        "lowLiquidationPriceMultiplier": lowLiquidationPriceMultiplier,
        "shortMutualRedeemPublicKey": shortPublicKey,
        "longMutualRedeemPublicKey": longPublicKey,
        "shortPayoutAddress": shortAddress,
        "longPayoutAddress": longAddress,
        "enableMutualRedemption": 1,
        "isSimpleHedge": 1,
    }

    parsed_fees = []
    if isinstance(fees, list):
        for fee in fees:
            if not isinstance(fee, dict):
                continue

            fee_address = fee.get("address")
            fee_satoshis = fee.get("satoshis")

            if not fee_address or not fee_satoshis:
                continue

            parsed_fees.append({
                "name": fee.get("name", ""),
                "description": fee.get("description", ""),
                "address": fee_address,
                "satoshis": fee_satoshis,
            })

    parsed_fundings = []
    if isinstance(fundings, list):
        for funding in fundings:
            if not isinstance(funding, dict):
                continue

            tx_hash = funding.get("tx_hash")
            funding_output = funding.get("funding_output")
            funding_satoshis = funding.get("funding_satoshis")

            valid_funding_output = isinstance(funding_output, int) and funding_output >= 0
            if not tx_hash or not valid_funding_output or not funding_satoshis:
                continue

            parsed_fundings.append(dict(
                txHash=tx_hash,
                fundingOutput=funding_output,
                fundingSatoshis=funding_satoshis,
            ))

    opts = None
    if contract_version:
        opts = dict(contractVersion=contract_version)

    return AnyhedgeFunctions.compileContract(data, parsed_fees, parsed_fundings, opts)


def compile_contract_from_hedge_position(hedge_position_obj):
    fees = []
    for fee in hedge_position_obj.fees.all():
        if not fee.address or not fee.satoshis:
            continue

        fees.append({
            "name": fee.name,
            "description": fee.description,
            "address": fee.address,
            "satoshis": fee.satoshis,
        })

    taker = ""
    try:
        if hedge_position_obj.metadata:
            taker = hedge_position_obj.metadata.position_taker
    except hedge_position_obj.__class__.metadata.RelatedObjectDoesNotExist:
        pass

    starting_oracle_message = hedge_position_obj.starting_oracle_message
    starting_oracle_signature = hedge_position_obj.starting_oracle_signature
    if (not starting_oracle_message or not starting_oracle_signature) and hedge_position_obj.price_oracle_message:
        starting_oracle_message = hedge_position_obj.price_oracle_message.message
        starting_oracle_signature = hedge_position_obj.price_oracle_message.signature
    
    fundings = []
    for funding_obj in hedge_position_obj.fundings.all():
        if not funding_obj.tx_hash or funding_obj.funding_output < 0 or not funding_obj.funding_satoshis:
            continue

        fundings.append(dict(
            tx_hash=funding_obj.tx_hash,
            funding_output=funding_obj.funding_output,
            funding_satoshis=funding_obj.funding_satoshis,
        ))

    return compile_contract(
        takerSide=taker,
        nominal_units=hedge_position_obj.nominal_units,
        oraclePublicKey=hedge_position_obj.oracle_pubkey,
        startingOracleMessage=starting_oracle_message,
        startingOracleSignature=starting_oracle_signature,
        maturityTimestamp=datetime.timestamp(hedge_position_obj.maturity_timestamp),
        highLiquidationPriceMultiplier=hedge_position_obj.high_liquidation_multiplier,
        lowLiquidationPriceMultiplier=hedge_position_obj.low_liquidation_multiplier,
        shortPublicKey=hedge_position_obj.short_pubkey,
        longPublicKey=hedge_position_obj.long_pubkey,
        shortAddress=hedge_position_obj.short_address,
        longAddress=hedge_position_obj.long_address,
        fees=fees,
        fundings=fundings,
        contract_version=hedge_position_obj.anyhedge_contract_version,
    )

def compile_contract_from_hedge_position_offer(hedge_position_offer_obj):
    duration_seconds = hedge_position_offer_obj.duration_seconds
    low_price_mult = hedge_position_offer_obj.low_liquidation_multiplier
    high_price_mult = hedge_position_offer_obj.high_liquidation_multiplier

    oracle_pubkey = hedge_position_offer_obj.oracle_pubkey
    start_price = hedge_position_offer_obj.counter_party_info.price_value
    start_timestamp = hedge_position_offer_obj.counter_party_info.price_message_timestamp
    maturity_timestamp = start_timestamp + timedelta(seconds=hedge_position_offer_obj.duration_seconds)
    starting_oracle_message = hedge_position_offer_obj.counter_party_info.starting_oracle_message
    starting_oracle_signature = hedge_position_offer_obj.counter_party_info.starting_oracle_signature
    if (not starting_oracle_message or not starting_oracle_signature) and hedge_position_offer_obj.counter_party_info.price_oracle_message:
        price_oracle_message = hedge_position_offer_obj.counter_party_info.price_oracle_message
        starting_oracle_message = price_oracle_message.message
        starting_oracle_signature = price_oracle_message.signature

    short_address = hedge_position_offer_obj.address
    short_pubkey = hedge_position_offer_obj.pubkey
    long_address = hedge_position_offer_obj.counter_party_info.address
    long_pubkey = hedge_position_offer_obj.counter_party_info.pubkey
    if hedge_position_offer_obj.position == HedgePositionOffer.POSITION_LONG:
        short_address, long_address = long_address, short_address
        short_pubkey, long_pubkey = long_pubkey, short_pubkey

    if hedge_position_offer_obj.position == HedgePositionOffer.POSITION_SHORT:
        contract_sats = hedge_position_offer_obj.satoshis
    else:
        contract_sats = calculate_hedge_sats(
            long_sats=hedge_position_offer_obj.satoshis,
            low_price_mult=low_price_mult,
            price_value=start_price,
        )

    nominal_units = contract_sats * start_price / 10 ** 8

    fees = []
    fee_address = hedge_position_offer_obj.counter_party_info.settlement_service_fee_address
    fee_satoshis = hedge_position_offer_obj.counter_party_info.settlement_service_fee
    
    if fee_address and fee_satoshis:
        fees.append({ "address": fee_address, "satoshis": fee_satoshis })

    return compile_contract(
        takerSide="long" if hedge_position_offer_obj.position == "short" else "short",
        nominal_units=nominal_units,
        oraclePublicKey=oracle_pubkey,
        startingOracleMessage=starting_oracle_message,
        startingOracleSignature=starting_oracle_signature,
        maturityTimestamp=maturity_timestamp.timestamp(),
        highLiquidationPriceMultiplier=high_price_mult,
        lowLiquidationPriceMultiplier=low_price_mult,
        shortPublicKey=short_pubkey,
        longPublicKey=long_pubkey,
        shortAddress=short_address,
        longAddress=long_address,
        fees=fees,
    )


def get_contract_status(
    contract_address, pubkey, signature,
    settlement_service_scheme="",
    settlement_service_domain="", 
    settlement_service_port=0,
    authentication_token="",
):
    return AnyhedgeFunctions.getContractStatus(
        contract_address,
        pubkey,
        signature,
        {
            "scheme": settlement_service_scheme,
            "domain": settlement_service_domain,
            "port": settlement_service_port,
            "authenticationToken": authentication_token,
        }
    )
