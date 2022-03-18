from unittest import mock
from django.test import TestCase, tag
from smartbch.tests.mocker import response_values as mock_responses

from smartbch.models import Transaction, Block, TokenContract
from smartbch.utils import transaction as transaction_utils

class TransactionUtilsTestCase(TestCase):
    @tag("unit")
    @mock.patch("web3.eth.Eth.get_transaction", return_value=mock_responses.test_tx)
    def test_save_transaction(self, mock_obj):
        txid = mock_obj.return_value.hash.hex()
        block_number = mock_obj.return_value.blockNumber

        tx_obj = transaction_utils.save_transaction(txid)
        self.assertTrue(
            Block.objects.filter(block_number=block_number).exists(),
            f"Expected to have {Block} record with block_number={block_number}"
        )
        self.assertIsInstance(tx_obj, Transaction)

    @tag("unit")
    @mock.patch("web3.eth.Eth.get_transaction_receipt", return_value=mock_responses.test_sep20_transfer_tx_receipt)
    @mock.patch("web3.eth.Eth.get_transaction", return_value=mock_responses.test_sep20_transfer_tx)
    def test_save_transaction_transfers(self, mock_tx, mock_tx_receipt):
        txid = mock_tx.return_value.hash.hex()
        token_contract_address = mock_tx_receipt.return_value.logs[0].address

        tx_obj = transaction_utils.save_transaction(txid)
        tx_obj = transaction_utils.save_transaction_transfers(txid)
        self.assertIsInstance(tx_obj, Transaction)
        self.assertTrue(
            tx_obj.transfers.filter(token_contract__isnull=False).count() > 0,
            f"Expected to have transfer record with token contract"
        )
        self.assertTrue(
            tx_obj.transfers.filter(token_contract__isnull=True).count() == 0,
            f"Expected to have no transfer record with no token contract"
        )
        self.assertTrue(
            TokenContract.objects.filter(address=token_contract_address).exists(),
            f"Expected to have {TokenContract} record with address={token_contract_address}"
        )
