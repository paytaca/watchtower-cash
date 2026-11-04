from unittest.mock import patch

import pytest
from celery.exceptions import Retry

import anyhedge.tasks as tasks


@pytest.fixture
def external_funding_mocks():
    with patch.object(tasks, "get_bchn_instance") as get_bchn, \
            patch.object(tasks, "Transaction") as transaction, \
            patch.object(tasks, "queue_post_broadcast_processing") as post_broadcast_processing:
        transaction.objects.filter.return_value.exists.return_value = False
        yield {
            "get_bchn": get_bchn,
            "transaction": transaction,
            "post_broadcast_processing": post_broadcast_processing,
        }


def test_indexes_funding_tx_broadcast_outside_watchtower(external_funding_mocks):
    external_funding_mocks["get_bchn"].return_value._get_raw_transaction.return_value = {
        "hex": "raw-tx-hex",
    }

    tasks.index_external_funding_transaction.run("txid-123")

    external_funding_mocks["get_bchn"].return_value._get_raw_transaction.assert_called_once_with(
        "txid-123"
    )
    external_funding_mocks["post_broadcast_processing"].assert_called_once_with(
        "txid-123", "raw-tx-hex"
    )


def test_retries_while_funding_tx_has_not_propagated_yet(external_funding_mocks):
    external_funding_mocks["get_bchn"].return_value._get_raw_transaction.return_value = None

    # Task.retry() defaults to throw=True, so Retry is raised even when the
    # task body is invoked directly via .run().
    with pytest.raises(Retry):
        tasks.index_external_funding_transaction.run("txid-123")

    external_funding_mocks["post_broadcast_processing"].assert_not_called()


def test_retries_when_raw_tx_lookup_fails(external_funding_mocks):
    external_funding_mocks["get_bchn"].return_value._get_raw_transaction.side_effect = Exception(
        "node unavailable"
    )

    with pytest.raises(Retry):
        tasks.index_external_funding_transaction.run("txid-123")

    external_funding_mocks["post_broadcast_processing"].assert_not_called()


def test_skips_funding_tx_that_is_already_indexed(external_funding_mocks):
    external_funding_mocks["get_bchn"].return_value._get_raw_transaction.return_value = {
        "hex": "raw-tx-hex",
    }
    external_funding_mocks["transaction"].objects.filter.return_value.exists.return_value = True

    tasks.index_external_funding_transaction.run("txid-123")

    external_funding_mocks["post_broadcast_processing"].assert_not_called()


def test_skips_empty_tx_hash(external_funding_mocks):
    tasks.index_external_funding_transaction.run("")

    external_funding_mocks["get_bchn"].assert_not_called()
    external_funding_mocks["post_broadcast_processing"].assert_not_called()
