from io import StringIO
from unittest import mock

from django.test import SimpleTestCase, TestCase

import cts.utils as cts_utils
from cts.utils import (
    assert_unspent_authhead,
    build_authchain,
    repair_authchain_full,
    repair_authchain_minimal,
)
from cts.management.commands.repair_authchain import Command
from main.models import Token, Transaction


def node_with_txs(txs):
    """A mock NODE whose BCH._get_raw_transaction(txid) returns txs.get(txid)."""
    node = mock.Mock()
    node.BCH._get_raw_transaction.side_effect = lambda txid: txs.get(txid)
    return node


class BuildAuthchainTests(SimpleTestCase):
    """build_authchain walks the node backwards via raw vin[0].txid; no DB."""

    def test_authhead_equals_authbase(self):
        node = node_with_txs({})
        with mock.patch.object(cts_utils, "NODE", node):
            self.assertEqual(build_authchain("A", "A"), ["A"])
        node.BCH._get_raw_transaction.assert_not_called()

    def test_happy_path(self):
        txs = {
            "H": {"vin": [{"txid": "B"}]},
            "B": {"vin": [{"txid": "A"}]},
        }
        with mock.patch.object(cts_utils, "NODE", node_with_txs(txs)):
            self.assertEqual(build_authchain("H", "A"), ["A", "B", "H"])

    def test_cycle_detected(self):
        txs = {
            "H": {"vin": [{"txid": "B"}]},
            "B": {"vin": [{"txid": "H"}]},
        }
        with mock.patch.object(cts_utils, "NODE", node_with_txs(txs)):
            with self.assertRaisesRegex(ValueError, "cycle"):
                build_authchain("H", "A")

    def test_max_depth(self):
        txs = {
            "H": {"vin": [{"txid": "B"}]},
            "B": {"vin": [{"txid": "C"}]},
            "C": {"vin": [{"txid": "A"}]},
        }
        with mock.patch.object(cts_utils, "NODE", node_with_txs(txs)):
            with self.assertRaisesRegex(ValueError, "max depth"):
                build_authchain("H", "A", max_depth=2)

    def test_missing_tx(self):
        txs = {"H": {"vin": [{"txid": "X"}]}}
        with mock.patch.object(cts_utils, "NODE", node_with_txs(txs)):
            with self.assertRaisesRegex(ValueError, "node has no tx"):
                build_authchain("H", "A")

    def test_no_inputs(self):
        txs = {"H": {"vin": []}}
        with mock.patch.object(cts_utils, "NODE", node_with_txs(txs)):
            with self.assertRaisesRegex(ValueError, "has no inputs"):
                build_authchain("H", "A")

    def test_coinbase_has_no_prevout_txid(self):
        txs = {"H": {"vin": [{"coinbase": "00"}]}}
        with mock.patch.object(cts_utils, "NODE", node_with_txs(txs)):
            with self.assertRaisesRegex(ValueError, "prevout txid"):
                build_authchain("H", "A")


class AssertUnspentAuthheadTests(SimpleTestCase):
    def test_spent_output_rejected(self):
        node = mock.Mock()
        node.BCH.get_tx_output.return_value = None
        with mock.patch.object(cts_utils, "NODE", node):
            with self.assertRaisesRegex(ValueError, "not an unspent output"):
                assert_unspent_authhead("H")

    def test_unspent_output_ok(self):
        node = mock.Mock()
        node.BCH.get_tx_output.return_value = {"value": 1000}
        with mock.patch.object(cts_utils, "NODE", node):
            assert_unspent_authhead("H")  # does not raise
        node.BCH.get_tx_output.assert_called_once_with("H", 0)


class RepairGuardTests(SimpleTestCase):
    """Both repair paths must refuse a spent authhead before writing anything."""

    def _spent_node(self):
        node = mock.Mock()
        node.BCH.get_tx_output.return_value = None
        return node

    def test_minimal_rejects_spent_head(self):
        with mock.patch.object(cts_utils, "NODE", self._spent_node()):
            with self.assertRaisesRegex(ValueError, "not an unspent output"):
                repair_authchain_minimal(["A", "H"])

    def test_full_rejects_spent_head(self):
        with mock.patch.object(cts_utils, "NODE", self._spent_node()):
            with self.assertRaisesRegex(ValueError, "not an unspent output"):
                repair_authchain_full(["A", "H"], "H")


class DbWalkTests(TestCase):
    """_db_walk mirrors Authhead.get_authhead: follow index-0 spending_txid to the unspent head."""

    def setUp(self):
        self.token = Token.objects.create(name="bch", tokenid="", token_ticker="BCH")

    def _txs(self, rows):
        # bulk_create bypasses the Transaction post-save signal (no node/cache calls).
        Transaction.objects.bulk_create([
            Transaction(
                txid=txid, index=0, spent=spent, spending_txid=spending_txid,
                token=self.token, source="test",
            )
            for txid, spent, spending_txid in rows
        ])

    def test_resolves_to_head(self):
        self._txs([("A", True, "H"), ("H", False, "")])
        row = Command._db_walk("A")
        self.assertIsNotNone(row)
        self.assertEqual(row.txid, "H")

    def test_missing_link_returns_none(self):
        self._txs([("A", True, "H")])  # H row absent
        self.assertIsNone(Command._db_walk("A"))

    def test_dangling_link_returns_none(self):
        self._txs([("A", True, "")])  # spent, no further link
        self.assertIsNone(Command._db_walk("A"))

    def test_missing_authbase_returns_none(self):
        self.assertIsNone(Command._db_walk("nope"))


class DiagnoseTests(TestCase):
    def setUp(self):
        self.token = Token.objects.create(name="bch", tokenid="", token_ticker="BCH")
        self.command = Command()
        self.command.stdout = StringIO()
        self.command.stderr = StringIO()

    def _txs(self, rows):
        Transaction.objects.bulk_create([
            Transaction(
                txid=txid, index=0, spent=spent, spending_txid=spending_txid,
                token=self.token, source="test",
            )
            for txid, spent, spending_txid in rows
        ])

    def test_resolved_verdict(self):
        self._txs([("A", True, "H"), ("H", False, "")])
        resolved_ok, resolved_txid = self.command._diagnose(["A", "H"], "H", "A")
        self.assertTrue(resolved_ok)
        self.assertEqual(resolved_txid, "H")

    def test_broken_verdict(self):
        self._txs([("A", True, "")])  # spent with no link -> walk resolves nothing
        resolved_ok, resolved_txid = self.command._diagnose(["A", "H"], "H", "A")
        self.assertFalse(resolved_ok)
        self.assertIsNone(resolved_txid)
