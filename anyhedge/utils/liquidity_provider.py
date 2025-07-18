import logging
import time
import functools
import requests
import decimal
from urllib.parse import urljoin
from django.conf import settings

from anyhedge import models
from .parser import AnyhedgeJSONParser

def ttl_hash(size=60*5):
    return round(time.time() / size)

LOGGER = logging.getLogger("stablehedge")

class GeneralProtocolsLP:
    json_parser = AnyhedgeJSONParser

    def __init__(self, base_url=settings.ANYHEDGE["ANYHEDGE_LP_BASE_URL"]):
        self.base_url = base_url

        self._session = requests.Session()
        self._session.headers["Accept"] = "application/json"
        self._session.headers["Content-Type"] = "application/json"

    def generate_url(self, path):
        base_url = self.base_url
        if not base_url or not isinstance(base_url, str): return
        if not isinstance(path, str): return

        # this ensures the urlpath in base_url is not overwritten in urljoin
        if not base_url.endswith("/"): base_url += "/"
        if path.startswith("/"): path = path[1:]

        return urljoin(base_url, path)

    def _request(self, method, url, *args, **kwargs):
        full_url = self.generate_url(url)
        if not full_url: Exception("Unable to construct api url")
        return self._session.request(method.upper(), full_url, *args, **kwargs)

    # ttl_hash in param is just to make run a new value every 2 minutes
    # source: https://stackoverflow.com/a/55900800/13022138
    @functools.lru_cache
    def liquidity_service_info(self, ttl_hash=ttl_hash(10)):
        print("Getting liquidity service")
        response = self._request("get", "/api/v2/liquidityServiceInformation")

        result = self.json_parser.parse(response.json())
        LOGGER.debug(f"LIQUIDITY SERVICE INFO | {response.url} | {self.json_parser.dumps(result, indent=2)}")
        return result

    def estimate_service_fee(self, contract_creation_parameters:dict, settlement_service:dict=None):
        data = self.json_parser.dumps(contract_creation_parameters)
        if settlement_service:
            scheme = settlement_service["scheme"]
            host = settlement_service["host"]
            port = settlement_service["port"]
            url = f"{scheme}://{host}:{port}/api/v2/estimateFee"
            response = requests.post(url,
                data = data,
                headers = {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
            )
        else:
            response = self._request("post", "/api/v2/estimateFee", data=data)
        parsed_data = self.json_parser.dumps(self.json_parser.loads(data), indent=2)
        result = self.json_parser.loads(response.content)
        LOGGER.debug(f"ESTIMATE SERVICE FEE | {response.url} | {parsed_data} | {self.json_parser.dumps(result, indent=2)}")
        return result

    def prepare_contract_position(self, oracle_public_key:str, pool_side:str):
        data = dict(oraclePublicKey=oracle_public_key, poolSide=pool_side)
        data = self.json_parser.dumps(data)
        response = self._request("post", "/api/v2/prepareContractPosition", data=data)

        parsed_data = self.json_parser.dumps(self.json_parser.loads(data), indent=2)
        result = self.json_parser.parse(response.json())
        LOGGER.debug(f"PREPARE CONTRACT POSITION | {response.url} | {parsed_data} | {self.json_parser.dumps(result, indent=2)}")
        return result

    def propose_contract(self, contract_proposal_data:dict):
        data = self.json_parser.dumps(contract_proposal_data)
        response = self._request("post", "/api/v2/proposeContract", data=data)
        
        parsed_data = self.json_parser.dumps(self.json_parser.loads(data), indent=2)
        result = self.json_parser.parse(response.json())
        LOGGER.debug(f"PROPOSE CONTRACT | {response.url} | {parsed_data} | {self.json_parser.dumps(result, indent=2)}")
        return result

    def propose_hedge_position(self, hedge_pos_obj:models.HedgePosition):
        contract_proposal_data = self.hedge_position_to_proposal(hedge_pos_obj)
        proposal_result = self.propose_contract(contract_proposal_data)
        return proposal_result

    @classmethod
    def fit_intent_to_constraints(
        cls,
        satoshis:int=0,
        low_liquidation_multiplier:float=0.5,
        high_liquidation_multiplier:float=0.5,
        duration_seconds:int=0,
        start_price:int=0,
        constraints:dict=None,
        is_simple_hedge:bool=True,
    ):
        min_sats = int((constraints["minimumNominalUnits"] * 10 ** 8) / start_price)
        max_sats = int((constraints["maximumNominalUnits"] * 10 ** 8) / start_price)
        satoshis = fit_range(satoshis, min_sats, max_sats)

        low_liquidation_multiplier = fit_range(low_liquidation_multiplier,
            constraints["minimumLowLiquidationPriceMultiplier"],
            constraints["maximumLowLiquidationPriceMultiplier"],
        )

        if is_simple_hedge:
            high_liquidation_multiplier = constraints["hedgeFixedHighLiquidationPriceMultiplier"]
        else:
            high_liquidation_multiplier = fit_range(high_liquidation_multiplier,
                constraints["minimumHighLiquidationPriceMultiplier"],
                constraints["maximumHighLiquidationPriceMultiplier"],
            )

        duration_seconds = fit_range(duration_seconds, # 1 day
            constraints["minimumDurationInSeconds"],
            constraints["maximumDurationInSeconds"],
        )

        return (
            satoshis,
            low_liquidation_multiplier,
            high_liquidation_multiplier,
            duration_seconds,
        )

    @classmethod
    def hedge_position_to_proposal(cls, hedge_pos_obj:models.HedgePosition):
        taker_side = hedge_pos_obj.metadata.position_taker
        if taker_side == "hedge":
            taker_side = "short"

        contract_creation_parameters = dict(
            takerSide = taker_side,
            makerSide = "short" if taker_side == "long" else "long",
            nominalUnits = hedge_pos_obj.nominal_units,
            oraclePublicKey = hedge_pos_obj.oracle_pubkey,
            startingOracleMessage = hedge_pos_obj.starting_oracle_message,
            startingOracleSignature = hedge_pos_obj.starting_oracle_signature,
            maturityTimestamp = decimal.Decimal(hedge_pos_obj.maturity_timestamp.timestamp()).quantize(0),
            highLiquidationPriceMultiplier = hedge_pos_obj.high_liquidation_multiplier,
            lowLiquidationPriceMultiplier = hedge_pos_obj.low_liquidation_multiplier,
            shortMutualRedeemPublicKey = hedge_pos_obj.short_pubkey,
            longMutualRedeemPublicKey = hedge_pos_obj.long_pubkey,
            shortPayoutAddress = hedge_pos_obj.short_address,
            longPayoutAddress = hedge_pos_obj.long_address,
            enableMutualRedemption = decimal.Decimal(1),
            isSimpleHedge = decimal.Decimal(1 if hedge_pos_obj.is_simple_hedge else 0),
        )

        # getting msg sequence from price message is based on this:
        # https://gitlab.com/GeneralProtocols/priceoracle/specification#price-messages
        message_sequence_hex = hedge_pos_obj.starting_oracle_message[8:16]
        message_sequence_bytes = bytes.fromhex(message_sequence_hex)
        starting_message_sequence = int.from_bytes(
            message_sequence_bytes, byteorder="little",
        )

        fees = []
        for fee in hedge_pos_obj.fees.all():
            fees.append(dict(
                name = fee.name,
                description = fee.description,
                address = fee.address,
                satoshis = fee.satoshis,
            ))

        return dict(
            contractCreationParameters = contract_creation_parameters,
            contractStartingOracleMessageSequence = starting_message_sequence,
            fees = fees,
        )

    @classmethod
    def contract_data_to_proposal(cls, contract_data:dict, price_obj:models.PriceOracleMessage=None):
        parameters = contract_data["parameters"]
        metadata = contract_data["metadata"]
        contract_creation_parameters = dict(
            takerSide = metadata["takerSide"],
            makerSide = metadata["makerSide"],
            nominalUnits = metadata["nominalUnits"],
            oraclePublicKey = parameters["oraclePublicKey"],
            startingOracleMessage = metadata["startingOracleMessage"],
            startingOracleSignature = metadata["startingOracleSignature"],
            maturityTimestamp = decimal.Decimal(parameters["maturityTimestamp"]),
            highLiquidationPriceMultiplier = metadata["highLiquidationPriceMultiplier"],
            lowLiquidationPriceMultiplier = metadata["lowLiquidationPriceMultiplier"],
            shortMutualRedeemPublicKey = parameters["shortMutualRedeemPublicKey"],
            longMutualRedeemPublicKey = parameters["longMutualRedeemPublicKey"],
            shortPayoutAddress = metadata["shortPayoutAddress"],
            longPayoutAddress = metadata["longPayoutAddress"],
            enableMutualRedemption = decimal.Decimal(parameters["enableMutualRedemption"]),
            isSimpleHedge = decimal.Decimal(metadata["isSimpleHedge"]),
        )

        if price_obj:
            starting_message_sequence = price_obj.message_sequence
        else:
            # getting msg sequence from price message is based on this:
            # https://gitlab.com/GeneralProtocols/priceoracle/specification#price-messages
            message_sequence_hex = metadata["startingOracleMessage"][8:16]
            message_sequence_bytes = bytes.fromhex(message_sequence_hex)
            starting_message_sequence = int.from_bytes(
                message_sequence_bytes, byteorder="little",
            )

        return dict(
            contractCreationParameters = contract_creation_parameters,
            contractStartingOracleMessageSequence = starting_message_sequence,
            fees = contract_data["fees"],
        )


def fit_range(value, min_val, max_val):
    value = max(value, min_val)
    value = min(value, max_val)
    return value
