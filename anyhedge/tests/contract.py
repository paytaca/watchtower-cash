import json
from django.test import TestCase

from anyhedge.utils.contract import (
    calculate_hedge_sats,
    compile_contract,
    compile_contract_from_hedge_position,
    compile_contract_from_hedge_position_offer,
)
from anyhedge.serializers import (
    HedgePositionSerializer,
    HedgePositionOfferSerializer,
)

from .data import (
    factory,
    hedge_position as hedge_position_data,
    hedge_position_offer as hedge_position_offer_data,
)

# Create your tests here.
class ContractCreationTestCase(TestCase):
    def test_calculate_hedge_sats(self):
        """
            Tests hedge sats calculation from long sats, used when compiling contracts from
            an hedge position offer
        """
        data = factory.generate_random_contract()
        contract_data = data["contract_data"]
        contract_creation_parameters = data["creation_parameters"]
        other = data["other"]
        price = other["price"]

        expected_hedge_sats = contract_data["metadata"]["hedgeInputInSatoshis"]
        calculated_hedge_sats = calculate_hedge_sats(
            long_sats=contract_data["metadata"]["longInputInSatoshis"],
            low_price_mult=contract_data["metadata"]["lowLiquidationPriceMultiplier"],
            price_value=contract_data["metadata"]["startPrice"],
        )

        sats_diff = abs(calculated_hedge_sats-expected_hedge_sats)
        sats_diff_pctg = (sats_diff/expected_hedge_sats) * 100
        self.assertTrue(0.0001 > sats_diff_pctg, f"Calculated hedge satoshis off by {sats_diff_pctg}% ({sats_diff}), expected {expected_hedge_sats} got {calculated_hedge_sats}")

    def test_compile_contract(self):
        data = factory.fetch_saved_test_data()
        self.assertIn("contract_data", data)

        contract_data = data["contract_data"]
        self.assertIn("address", contract_data)
        self.assertIn("version", contract_data)
        self.assertIn("parameters", contract_data)
        self.assertIn("metadata", contract_data)


    def test_compile_contract_from_hedge_position(self):
        contract, _, _ = hedge_position_data.load_test_data()
        contract_data = compile_contract_from_hedge_position(contract)
        contract_metadata = contract_data["metadata"]
        contract_parameters = contract_data["parameters"]

        self.assertIs(type(contract_data), dict)
        self.assertEqual(
            contract.address,
            contract_data["address"],
            f"Generated different addressses:\n" \
            f"\tmodel={json.dumps(HedgePositionSerializer(contract).data, indent=4)}\n" \
            f"\tcontract_data={json.dumps(contract_data, indent=4)}"
        )
        self.assertEqual(contract.satoshis, contract_metadata["hedgeInputInSatoshis"])

        self.assertEqual(contract.start_timestamp.timestamp(), contract_parameters["startTimestamp"])
        self.assertEqual(contract.maturity_timestamp.timestamp(), contract_parameters["maturityTimestamp"])

        self.assertEqual(contract.hedge_address, contract_metadata["hedgePayoutAddress"])
        self.assertEqual(contract.hedge_pubkey, contract_parameters["hedgeMutualRedeemPublicKey"])
        self.assertEqual(contract.long_address, contract_metadata["longPayoutAddress"])
        self.assertEqual(contract.long_pubkey, contract_parameters["longMutualRedeemPublicKey"])

        self.assertEqual(contract.oracle_pubkey, contract_parameters["oraclePublicKey"])

        self.assertEqual(contract.start_price, contract_metadata["startPrice"])
        self.assertEqual(contract.low_liquidation_multiplier, contract_metadata["lowLiquidationPriceMultiplier"])
        self.assertEqual(contract.high_liquidation_multiplier, contract_metadata["highLiquidationPriceMultiplier"])


    def test_compile_contract_from_hedge_position_offer(self):
        contract_position_offer, _, _ = hedge_position_offer_data.load_test_data()
        contract_data = compile_contract_from_hedge_position_offer(contract_position_offer)

        contract_metadata = contract_data["metadata"]
        contract_parameters = contract_data["parameters"]

        self.assertIs(type(contract_data), dict)
        self.assertEqual(
            contract_position_offer.counter_party_info.contract_address,
            contract_data["address"],
            f"Generated different addressses:\n" \
            f"\toffer={json.dumps(HedgePositionOfferSerializer(contract_position_offer).data, indent=4)}\n" \
            f"\tcontract_data={json.dumps(contract_data, indent=4)}"
        )
