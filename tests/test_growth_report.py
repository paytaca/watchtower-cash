from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from main.models import Address, Project, Token, Wallet, WalletHistory


def _utc_date_str(dt):
    """Return YYYY-MM-DD string for a timezone-aware datetime (in UTC)."""
    return dt.strftime("%Y-%m-%d")


class GrowthReportViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.project = Project.objects.create(name="paytaca")
        self.bch_token = Token.objects.create(
            name="bch",
            tokenid="",
            token_ticker="BCH",
        )
        self.slp_token = Token.objects.create(
            name="spice",
            tokenid="abc123",
            token_ticker="SPICE",
        )

        # BCH wallet
        self.wallet_a = Wallet.objects.create(
            wallet_hash="wallet_a_hash",
            wallet_type="bch",
            version=2,
            project=self.project,
        )
        self.wallet_b = Wallet.objects.create(
            wallet_hash="wallet_b_hash",
            wallet_type="bch",
            version=2,
            project=self.project,
        )
        # SLP wallet (should be excluded)
        self.wallet_slp = Wallet.objects.create(
            wallet_hash="wallet_slp_hash",
            wallet_type="slp",
            version=2,
            project=self.project,
        )

        self.addr_a = Address.objects.create(
            address="bitcoincash:qaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            address_path="0/0",
            wallet=self.wallet_a,
            project=self.project,
        )
        self.addr_b = Address.objects.create(
            address="bitcoincash:qbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            address_path="0/0",
            wallet=self.wallet_b,
            project=self.project,
        )

        self.url = reverse("growth-report")
        self.report_date = timezone.now().date()
        self.date_str = _utc_date_str(timezone.now())

    def _create_wallet_history(self, **kwargs):
        defaults = {
            "wallet": self.wallet_a,
            "txid": "default_txid",
            "record_type": WalletHistory.INCOMING,
            "amount": 1.0,
            "token": self.bch_token,
            "tx_timestamp": timezone.now(),
        }
        defaults.update(kwargs)
        return WalletHistory.objects.create(**defaults)

    # ── Response shape & validation ────────────────────────────────

    def test_response_has_all_expected_keys(self):
        response = self.client.get(self.url, {"date": self.date_str})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["date"], self.date_str)
        self.assertEqual(data["project"], "paytaca")

        for key in [
            "new_wallets",
            "cumulative_wallets",
            "daily_active_wallets",
            "active_wallets_via_transactions",
        ]:
            self.assertIn(key, data["wallets"])

        for key in ["new_addresses", "cumulative_addresses"]:
            self.assertIn(key, data["addresses"])

        for key in [
            "total_transactions",
            "incoming_transactions",
            "outgoing_transactions",
            "total_transaction_records",
            "incoming_transaction_records",
            "outgoing_transaction_records",
            "total_bch_volume",
            "incoming_bch_volume",
            "outgoing_bch_volume",
            "total_usd_volume",
            "incoming_usd_volume",
            "outgoing_usd_volume",
            "average_bch_record_value",
            "average_usd_record_value",
            "total_tx_fees",
            "active_sending_wallets",
            "active_receiving_wallets",
        ]:
            self.assertIn(key, data["transactions"])

        for key in [
            "transactions_per_active_wallet",
            "net_bch_flow",
        ]:
            self.assertIn(key, data["engagement"])

    def test_invalid_date_format_returns_400(self):
        response = self.client.get(self.url, {"date": "not-a-date"})
        self.assertEqual(response.status_code, 400)

    def test_nonexistent_project_returns_400(self):
        response = self.client.get(
            self.url, {"date": self.date_str, "project": "nonexistent"}
        )
        self.assertEqual(response.status_code, 400)

    def test_default_project_is_paytaca(self):
        response = self.client.get(self.url, {"date": self.date_str})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["project"], "paytaca")

    # ── Wallet metrics ─────────────────────────────────────────────

    def test_new_wallets_count(self):
        response = self.client.get(self.url, {"date": self.date_str})
        self.assertEqual(response.status_code, 200)
        # 2 BCH wallets created today (setUp), SLP wallet excluded
        self.assertEqual(response.json()["wallets"]["new_wallets"], 2)

    def test_cumulative_wallets_count(self):
        # Create a wallet on a previous day
        Wallet.objects.create(
            wallet_hash="old_wallet",
            wallet_type="bch",
            version=2,
            project=self.project,
            date_created=timezone.now() - timedelta(days=5),
        )
        response = self.client.get(self.url, {"date": self.date_str})
        self.assertEqual(response.json()["wallets"]["cumulative_wallets"], 3)

    def test_daily_active_wallets(self):
        self.wallet_a.last_balance_check = timezone.now()
        self.wallet_a.save()
        response = self.client.get(self.url, {"date": self.date_str})
        self.assertEqual(response.json()["wallets"]["daily_active_wallets"], 1)

    # ── Transaction counts (distinct txid vs records) ─────────────

    def test_transaction_vs_record_counts(self):
        """A single txid with both incoming and outgoing records:
        total_transactions=1 but total_transaction_records=2."""
        self._create_wallet_history(
            wallet=self.wallet_a,
            txid="shared_txid",
            record_type=WalletHistory.OUTGOING,
            amount=1.0,
        )
        self._create_wallet_history(
            wallet=self.wallet_b,
            txid="shared_txid",
            record_type=WalletHistory.INCOMING,
            amount=1.0,
        )
        response = self.client.get(self.url, {"date": self.date_str})
        tx = response.json()["transactions"]

        self.assertEqual(tx["total_transactions"], 1)
        self.assertEqual(tx["incoming_transactions"], 1)
        self.assertEqual(tx["outgoing_transactions"], 1)
        self.assertEqual(tx["total_transaction_records"], 2)
        self.assertEqual(tx["incoming_transaction_records"], 1)
        self.assertEqual(tx["outgoing_transaction_records"], 1)

    # ── Fee aggregation (no double counting) ───────────────────────

    def test_tx_fees_not_double_counted(self):
        """Same txid with two records: fee should be counted once."""
        self._create_wallet_history(
            wallet=self.wallet_a,
            txid="fee_test_txid",
            record_type=WalletHistory.OUTGOING,
            amount=1.0,
            tx_fee=0.0001,
        )
        self._create_wallet_history(
            wallet=self.wallet_b,
            txid="fee_test_txid",
            record_type=WalletHistory.INCOMING,
            amount=1.0,
            tx_fee=0.0001,
        )
        response = self.client.get(self.url, {"date": self.date_str})
        self.assertEqual(
            response.json()["transactions"]["total_tx_fees"],
            round(0.0001, 8),
        )

    # ── Volume & averages ──────────────────────────────────────────

    def test_bch_volume(self):
        self._create_wallet_history(
            wallet=self.wallet_a,
            txid="vol_in_txid",
            record_type=WalletHistory.INCOMING,
            amount=2.5,
        )
        self._create_wallet_history(
            wallet=self.wallet_a,
            txid="vol_out_txid",
            record_type=WalletHistory.OUTGOING,
            amount=1.0,
        )
        response = self.client.get(self.url, {"date": self.date_str})
        tx = response.json()["transactions"]

        self.assertEqual(tx["total_bch_volume"], round(3.5, 8))
        self.assertEqual(tx["incoming_bch_volume"], round(2.5, 8))
        self.assertEqual(tx["outgoing_bch_volume"], round(1.0, 8))

    def test_usd_volume(self):
        self._create_wallet_history(
            wallet=self.wallet_a,
            txid="usd_txid",
            record_type=WalletHistory.INCOMING,
            amount=2.0,
            usd_price=Decimal("100.00"),
        )
        response = self.client.get(self.url, {"date": self.date_str})
        tx = response.json()["transactions"]

        self.assertEqual(tx["total_usd_volume"], 200.0)
        self.assertEqual(tx["incoming_usd_volume"], 200.0)
        self.assertEqual(tx["outgoing_usd_volume"], 0.0)

    def test_average_record_value(self):
        self._create_wallet_history(
            wallet=self.wallet_a,
            txid="avg1_txid",
            record_type=WalletHistory.INCOMING,
            amount=3.0,
        )
        self._create_wallet_history(
            wallet=self.wallet_a,
            txid="avg2_txid",
            record_type=WalletHistory.OUTGOING,
            amount=1.0,
        )
        response = self.client.get(self.url, {"date": self.date_str})
        tx = response.json()["transactions"]

        # (3.0 + 1.0) / 2 records = 2.0
        self.assertEqual(tx["average_bch_record_value"], round(2.0, 8))

    def test_net_bch_flow(self):
        self._create_wallet_history(
            wallet=self.wallet_a,
            txid="flow_in_txid",
            record_type=WalletHistory.INCOMING,
            amount=5.0,
        )
        self._create_wallet_history(
            wallet=self.wallet_a,
            txid="flow_out_txid",
            record_type=WalletHistory.OUTGOING,
            amount=2.0,
        )
        response = self.client.get(self.url, {"date": self.date_str})
        self.assertEqual(
            response.json()["engagement"]["net_bch_flow"],
            round(3.0, 8),
        )

    # ── Exclusion of non-BCH wallets/tokens ────────────────────────

    def test_slp_wallet_excluded(self):
        self._create_wallet_history(
            wallet=self.wallet_slp,
            txid="slp_txid",
            record_type=WalletHistory.INCOMING,
            amount=10.0,
        )
        response = self.client.get(self.url, {"date": self.date_str})
        tx = response.json()["transactions"]
        self.assertEqual(tx["total_transactions"], 0)
        self.assertEqual(tx["total_bch_volume"], 0)

    def test_non_bch_token_excluded(self):
        self._create_wallet_history(
            wallet=self.wallet_a,
            txid="slp_token_txid",
            record_type=WalletHistory.INCOMING,
            amount=10.0,
            token=self.slp_token,
        )
        response = self.client.get(self.url, {"date": self.date_str})
        tx = response.json()["transactions"]
        self.assertEqual(tx["total_transactions"], 0)

    # ── Date filtering ─────────────────────────────────────────────

    def test_transactions_outside_date_excluded(self):
        self._create_wallet_history(
            wallet=self.wallet_a,
            txid="old_txid",
            record_type=WalletHistory.INCOMING,
            amount=5.0,
            tx_timestamp=timezone.now() - timedelta(days=3),
        )
        response = self.client.get(self.url, {"date": self.date_str})
        tx = response.json()["transactions"]
        self.assertEqual(tx["total_transactions"], 0)

    def test_null_tx_timestamp_falls_back_to_date_created(self):
        self._create_wallet_history(
            wallet=self.wallet_a,
            txid="null_ts_txid",
            record_type=WalletHistory.INCOMING,
            amount=1.0,
            tx_timestamp=None,
        )
        response = self.client.get(self.url, {"date": self.date_str})
        tx = response.json()["transactions"]
        self.assertEqual(tx["total_transactions"], 1)

    # ── Active wallets ─────────────────────────────────────────────

    def test_active_sending_and_receiving_wallets(self):
        self._create_wallet_history(
            wallet=self.wallet_a,
            txid="send_txid",
            record_type=WalletHistory.OUTGOING,
            amount=1.0,
        )
        self._create_wallet_history(
            wallet=self.wallet_b,
            txid="recv_txid",
            record_type=WalletHistory.INCOMING,
            amount=1.0,
        )
        response = self.client.get(self.url, {"date": self.date_str})
        tx = response.json()["transactions"]

        self.assertEqual(tx["active_sending_wallets"], 1)
        self.assertEqual(tx["active_receiving_wallets"], 1)

    # ── Empty data ─────────────────────────────────────────────────

    def test_empty_data_returns_zeros(self):
        response = self.client.get(
            self.url, {"date": "2020-01-01", "project": "paytaca"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["wallets"]["new_wallets"], 0)
        self.assertEqual(data["wallets"]["cumulative_wallets"], 0)
        self.assertEqual(data["transactions"]["total_transactions"], 0)
        self.assertEqual(data["transactions"]["total_bch_volume"], 0)
        self.assertEqual(data["transactions"]["total_tx_fees"], 0)
        self.assertEqual(data["engagement"]["net_bch_flow"], 0)
