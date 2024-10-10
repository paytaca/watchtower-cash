import time
import functools
import requests
from urllib.parse import urljoin
from django.conf import settings

from anyhedge import models
from .parser import AnyhedgeJSONParser

def ttl_hash(size=60*5):
    return round(time.time() / size)

class GeneralProtocolsLP:
    json_parser = AnyhedgeJSONParser

    def __init__(self, base_url=settings.ANYHEDGE["ANYHEDGE_LP_BASE_URL"]):
        self.base_url = base_url

        self._session = requests.Session()
        self._session.headers["Accept"] = "application/json"

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
        return self.json_parser.parse(response.json())

    def prepare_contract_position(self, oracle_public_key:str, pool_side:str):
        data = dict(oraclePublicKey=oracle_public_key, poolSide=pool_side)
        response = self._request("post", "/api/v2/prepareContractPosition", data=data)
        return self.json_parser.parse(response.json())

    def propose_contract(self, contract_proposal_data:dict):
        data = self.json_parser.dumps(contract_proposal_data)
        response = self._request("post", "/api/v2/proposeContract", data=data)
        return self.json_parser.parse(response.json())

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
            fees = [],
        )
