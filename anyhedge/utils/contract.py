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

    return AnyhedgeFunctions.compileContract(data, fee)


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
