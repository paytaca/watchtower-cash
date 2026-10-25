from unittest.mock import patch

import pytest

import anyhedge.utils.api as api


@pytest.fixture
def broadcast_mocks():
    with patch.object(api, "bitcoin") as bitcoin, \
            patch.object(api, "Transaction") as transaction, \
            patch.object(api, "broadcast_transaction_sync") as broadcast_sync, \
            patch.object(api, "process_mempool_transaction_fast") as mempool_processing, \
            patch.object(api, "send_post_broadcast_notifications_task") as notifications:
        bitcoin.txhash.return_value = "txid-123"
        transaction.objects.filter.return_value.exists.return_value = False
        yield {
            "transaction": transaction,
            "broadcast_sync": broadcast_sync,
            "mempool_processing": mempool_processing,
            "notifications": notifications,
        }


def test_uses_shared_broadcast_helper_and_queues_post_broadcast_processing(broadcast_mocks):
    broadcast_mocks["broadcast_sync"].return_value = {
        "success": True,
        "txid": "txid-123",
        "error": None,
    }

    result = api.broadcast_transaction("raw-tx-hex")

    assert result == {"success": True, "txid": "txid-123"}
    broadcast_mocks["broadcast_sync"].assert_called_once_with("raw-tx-hex")
    broadcast_mocks["mempool_processing"].delay.assert_called_once_with("txid-123", "raw-tx-hex", True)
    broadcast_mocks["notifications"].delay.assert_called_once_with("raw-tx-hex")


def test_returns_error_and_skips_processing_when_broadcast_fails(broadcast_mocks):
    broadcast_mocks["broadcast_sync"].return_value = {
        "success": False,
        "txid": None,
        "error": "transaction rejected by mempool",
    }

    result = api.broadcast_transaction("raw-tx-hex")

    assert result == {"success": False, "error": "transaction rejected by mempool"}
    broadcast_mocks["mempool_processing"].delay.assert_not_called()
    broadcast_mocks["notifications"].delay.assert_not_called()


def test_skips_broadcast_when_transaction_is_already_known(broadcast_mocks):
    broadcast_mocks["transaction"].objects.filter.return_value.exists.return_value = True

    result = api.broadcast_transaction("raw-tx-hex")

    assert result == {"success": True, "txid": "txid-123"}
    broadcast_mocks["broadcast_sync"].assert_not_called()
    broadcast_mocks["mempool_processing"].delay.assert_not_called()
    broadcast_mocks["notifications"].delay.assert_not_called()
