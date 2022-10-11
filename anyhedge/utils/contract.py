from datetime import datetime
from ..js.runner import AnyhedgeFunctions

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
    fee_output = -1
    fee_satoshis = 0
    funding = hedge_position_obj.get_hedge_position_funding()
    if funding:
        funding_output = funding.funding_output
        funding_satoshis = funding.funding_satoshis
        fee_output = funding.fee_output
        fee_satoshis = funding.fee_satoshis

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
        funding_fee_output=fee_output,
        funding_fee_satoshis=fee_satoshis,
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
