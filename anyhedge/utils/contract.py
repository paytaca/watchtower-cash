from datetime import datetime
from ..js.runner import AnyhedgeFunctions
from ..models import HedgePositionOffer


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
    hedge_address:str="",
    hedge_pubkey:str="",
    short_address:str="",
    short_pubkey:str="",
    oracle_pubkey:str=None,
    price_oracle_message_sequence:int=None,
):
    intent =  {
        "amount": satoshis/10**8,
        "lowPriceMult": low_price_multiplier,
        "highPriceMult": high_price_multiplier,
        "duration": duration_seconds,
    }
    pubkeys = {
        "hedgeAddress": hedge_address,
        "hedgePubkey": hedge_pubkey,
        "shortAddress": short_address,
        "shortPubkey": short_pubkey,
    }

    priceMessageConfig = None
    if oracle_pubkey:
        priceMessageConfig = {
            "oraclePubKey": oracle_pubkey,
        }

    priceMessageRequestParams = None
    if price_oracle_message_sequence:
        priceMessageRequestParams = {
            "minMessageSequence": price_oracle_message_sequence,
            "maxMessageSequence": price_oracle_message_sequence,
        }
    return AnyhedgeFunctions.create(intent, pubkeys, priceMessageConfig, priceMessageRequestParams)

def compile_contract(
    nominal_units:int=0,
    duration:int=0,
    startPrice:int=0,
    startTimestamp:int=0,
    oraclePublicKey:str="",
    highLiquidationPriceMultiplier:float=0.0,
    lowLiquidationPriceMultiplier:float=0.0,
    hedgePublicKey:str="",
    longPublicKey:str="",
    hedgeAddress:str="",
    longAddress:str="",
    fee_address:str="",
    fee_satoshis:int=0,
    funding_tx_hash:str=None,
    funding_output:int=-1,
    funding_satoshis:int=0,
    funding_fee_output:int=-1,
    funding_fee_satoshis:int=0,
):
    data = {
        "nominalUnits": nominal_units,
        "duration": duration,
        "startPrice": startPrice,
        "startTimestamp": startTimestamp,
        "oraclePublicKey": oraclePublicKey,
        "highLiquidationPriceMultiplier": highLiquidationPriceMultiplier,
        "lowLiquidationPriceMultiplier": lowLiquidationPriceMultiplier,
        "hedgePublicKey": hedgePublicKey,
        "longPublicKey": longPublicKey,
        "hedgeAddress": hedgeAddress,
        "longAddress": longAddress,
    }
    fee = None
    if fee_address and fee_satoshis:
        fee = { "address": fee_address, "satoshis": fee_satoshis }

    funding = None
    if funding_tx_hash and isinstance(funding_output, int) and funding_output >= 0:
        funding = {
            "txHash": funding_tx_hash,
            "fundingOutput": funding_output,
            "fundingSatoshis": funding_satoshis,
        }
        if isinstance(funding_fee_output, int) and funding_fee_output >= 0:
            funding["feeOutput"] = funding_fee_output
            funding["feeSatoshis"] = funding_fee_satoshis

    return AnyhedgeFunctions.compileContract(data, fee, funding)


def compile_contract_from_hedge_position(hedge_position_obj):
    fee_address = ""
    fee_satoshis = 0
    try:
        fee_address = hedge_position_obj.fee.address
        fee_satoshis = hedge_position_obj.fee.satoshis
    except hedge_position_obj.__class__.fee.RelatedObjectDoesNotExist:
        pass

    funding_output = -1
    funding_satoshis = 0
    funding_fee_output = -1
    funding_fee_satoshis = 0
    funding = hedge_position_obj.get_hedge_position_funding()
    if funding:
        funding_output = funding.funding_output
        funding_satoshis = funding.funding_satoshis
        funding_fee_output = funding.fee_output
        funding_fee_satoshis = funding.fee_satoshis

    return compile_contract(
        nominal_units=hedge_position_obj.nominal_units,
        duration=hedge_position_obj.duration_seconds,
        startPrice=hedge_position_obj.start_price,
        startTimestamp=datetime.timestamp(hedge_position_obj.start_timestamp),
        oraclePublicKey=hedge_position_obj.oracle_pubkey,
        highLiquidationPriceMultiplier=hedge_position_obj.high_liquidation_multiplier,
        lowLiquidationPriceMultiplier=hedge_position_obj.low_liquidation_multiplier,
        hedgePublicKey=hedge_position_obj.hedge_pubkey,
        longPublicKey=hedge_position_obj.long_pubkey,
        hedgeAddress=hedge_position_obj.hedge_address,
        longAddress=hedge_position_obj.long_address,
        fee_address=fee_address,
        fee_satoshis=fee_satoshis,
        funding_tx_hash=hedge_position_obj.funding_tx_hash,
        funding_output=funding_output,
        funding_satoshis=funding_satoshis,
        funding_fee_output=funding_fee_output,
        funding_fee_satoshis=funding_fee_satoshis,
    )

def compile_contract_from_hedge_position_offer(hedge_position_offer_obj):
    duration_seconds = hedge_position_offer_obj.duration_seconds
    low_price_mult = hedge_position_offer_obj.low_liquidation_multiplier
    high_price_mult = hedge_position_offer_obj.high_liquidation_multiplier

    oracle_pubkey = hedge_position_offer_obj.oracle_pubkey
    start_price = hedge_position_offer_obj.counter_party_info.price_value
    start_timestamp = hedge_position_offer_obj.counter_party_info.price_message_timestamp

    hedge_address = hedge_position_offer_obj.address
    hedge_pubkey = hedge_position_offer_obj.pubkey
    long_address = hedge_position_offer_obj.counter_party_info.address
    long_pubkey = hedge_position_offer_obj.counter_party_info.pubkey
    if hedge_position_offer_obj.position == HedgePositionOffer.POSITION_LONG:
        hedge_address, long_address = long_address, hedge_address
        hedge_pubkey, long_pubkey = long_pubkey, hedge_pubkey

    if hedge_position_offer_obj.position == HedgePositionOffer.POSITION_HEDGE:
        contract_sats = hedge_position_offer_obj.satoshis
    else:
        contract_sats = calculate_hedge_sats(
            long_sats=hedge_position_offer_obj.satoshis,
            low_price_mult=low_price_mult,
            price_value=start_price,
        )

    nominal_units = contract_sats * start_price / 10 ** 8

    return compile_contract(
        nominal_units=nominal_units,
        duration=duration_seconds,
        startPrice=start_price,
        startTimestamp=datetime.timestamp(start_timestamp),
        oraclePublicKey=oracle_pubkey,
        highLiquidationPriceMultiplier=high_price_mult,
        lowLiquidationPriceMultiplier=low_price_mult,
        hedgePublicKey=hedge_pubkey,
        longPublicKey=long_pubkey,
        hedgeAddress=hedge_address,
        longAddress=long_address,
        fee_address=hedge_position_offer_obj.counter_party_info.settlement_service_fee_address,
        fee_satoshis=hedge_position_offer_obj.counter_party_info.settlement_service_fee,
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
