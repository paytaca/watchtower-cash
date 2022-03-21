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

    @tag("unit")
    @mock.patch("smartbch.utils.web3.SmartBCHModule.query_transfer_events", return_value=mock_responses.test_sbch_query_transfer_events)
    @mock.patch("smartbch.utils.web3.SmartBCHModule.query_tx_by_addr", return_value=mock_responses.test_sbch_query_tx_by_addr)
    def test_get_transactions_by_address(self, mock_sbch_query_txs, mock_sbch_query_transfer_events):
        test_address = "0xdA34Ad1848424CCa7e0ff55C7EF6c6fE46833456"

        yield_txs = []
        # mockers will probably be run here
        iterator = transaction_utils.get_transactions_by_address(
            address=test_address,
            from_block=0,
            to_block=500,
            block_partition=0
        )
        for tx_list in iterator:
            yield_txs = [*yield_txs, *tx_list.transactions]
        
        yield_txs_hash = {tx.hash for tx in yield_txs}
        txs_in_mock_responses = set()
        for sbch_tx in mock_sbch_query_txs.return_value:
            txs_in_mock_responses.add(sbch_tx.hash)

        for log in mock_sbch_query_transfer_events.return_value:
            txs_in_mock_responses.add(
                log.transactionHash.hex()
            )

        missing_txs_in_yield = txs_in_mock_responses - yield_txs_hash
        unexpected_yield_txs = yield_txs_hash - txs_in_mock_responses

        self.assertTrue(
            len(missing_txs_in_yield) == 0,
            f"Got missing txs expected to be in yield: {missing_txs_in_yield}"
        )
        self.assertTrue(
            len(unexpected_yield_txs) == 0,
            f"Yielded transactions not in test responses: {unexpected_yield_txs}"
        )
