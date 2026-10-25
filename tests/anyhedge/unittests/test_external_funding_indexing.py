from unittest.mock import patch

import pytest
from celery.exceptions import Retry

import anyhedge.tasks as tasks


@pytest.fixture
def external_funding_mocks():
    with patch.object(tasks, "get_bchn_instance") as get_bchn, \
            patch.object(tasks, "Transaction") as transaction, \
            patch.object(tasks, "process_mempool_transaction_fast") as mempool_processing, \
            patch.object(tasks, "send_post_broadcast_notifications_task") as notifications:
        transaction.objects.filter.return_value.exists.return_value = False
        yield {
            "get_bchn": get_bchn,
            "transaction": transaction,
            "mempool_processing": mempool_processing,
            "notifications": notifications,
        }


def test_indexes_funding_tx_broadcast_outside_watchtower(external_funding_mocks):
    external_funding_mocks["get_bchn"].return_value._get_raw_transaction.return_value = {
        "hex": "raw-tx-hex",
    }

    tasks.index_external_funding_transaction.run("txid-123")

    external_funding_mocks["get_bchn"].return_value._get_raw_transaction.assert_called_once_with(
        "txid-123"
    )
    external_funding_mocks["mempool_processing"].delay.assert_called_once_with(
        "txid-123", "raw-tx-hex", immediate=True
    )
    external_funding_mocks["notifications"].delay.assert_called_once_with("raw-tx-hex")


def test_retries_while_funding_tx_has_not_propagated_yet(external_funding_mocks):
    external_funding_mocks["get_bchn"].return_value._get_raw_transaction.return_value = None

    with pytest.raises(Retry):
        tasks.index_external_funding_transaction.run("txid-123")

    external_funding_mocks["mempool_processing"].delay.assert_not_called()
    external_funding_mocks["notifications"].delay.assert_not_called()


def test_skips_funding_tx_that_is_already_indexed(external_funding_mocks):
    external_funding_mocks["get_bchn"].return_value._get_raw_transaction.return_value = {
        "hex": "raw-tx-hex",
    }
    external_funding_mocks["transaction"].objects.filter.return_value.exists.return_value = True

    tasks.index_external_funding_transaction.run("txid-123")

    external_funding_mocks["mempool_processing"].delay.assert_not_called()
    external_funding_mocks["notifications"].delay.assert_not_called()


def test_skips_empty_tx_hash(external_funding_mocks):
    tasks.index_external_funding_transaction.run("")

    external_funding_mocks["get_bchn"].assert_not_called()
    external_funding_mocks["mempool_processing"].delay.assert_not_called()
    external_funding_mocks["notifications"].delay.assert_not_called()
