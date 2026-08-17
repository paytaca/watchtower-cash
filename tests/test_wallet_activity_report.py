from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from main.models import Project, Token, Wallet, WalletActivity, WalletHistory


def _utc_date_str(dt):
    return dt.strftime("%Y-%m-%d")


class WalletActivityReportViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.project = Project.objects.create(name="paytaca")
        self.bch_token = Token.objects.create(
            name="bch",
            tokenid="",
            token_ticker="BCH",
        )
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
        self.url = reverse("wallet-activity-report")
        self.today = timezone.now().date()
        self.date_str = _utc_date_str(timezone.now())

    def _create_history(self, **kwargs):
        defaults = {
            "wallet": self.wallet_a,
            "txid": "txid_%s" % (WalletHistory.objects.count() + 1),
            "record_type": WalletHistory.OUTGOING,
            "amount": 1.0,
            "token": self.bch_token,
            "tx_timestamp": timezone.now(),
        }
        defaults.update(kwargs)
        return WalletHistory.objects.create(**defaults)

    def _create_activity(self, history=None, kind=None, wallet=None, day=None):
        return WalletActivity.objects.create(
            wallet=wallet or self.wallet_a,
            history=history,
            kind=kind or WalletActivity.KIND_TRANSACTION_SEND,
            activity_date=day or self.today,
        )

    def test_empty_day_returns_empty_results(self):
        response = self.client.get(self.url, {"date": "2020-01-01"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["results"], [])
        self.assertEqual(data["count"], 0)
        self.assertFalse(data["has_next"])

    def test_event_id_is_wallet_activity_id_not_txid(self):
        history = self._create_history(txid="abc123")
        activity = self._create_activity(history=history)
        response = self.client.get(self.url, {"date": self.date_str})
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        entry = data["results"][0]
        self.assertEqual(entry["event_id"], str(activity.id))
        self.assertNotEqual(entry["event_id"], "abc123")

    def test_transaction_send_returns_txid_and_sats_amount(self):
        history = self._create_history(txid="send_txid", amount=1.0)
        self._create_activity(history=history, kind=WalletActivity.KIND_TRANSACTION_SEND)
        response = self.client.get(self.url, {"date": self.date_str})
        entry = response.json()["results"][0]
        self.assertEqual(entry["kind"], WalletActivity.KIND_TRANSACTION_SEND)
        self.assertEqual(entry["txid"], "send_txid")
        self.assertEqual(entry["amount"], 100_000_000)

    def test_app_opening_has_null_txid_and_amount(self):
        self._create_activity(kind=WalletActivity.KIND_APP_OPENING)
        response = self.client.get(self.url, {"date": self.date_str})
        entry = response.json()["results"][0]
        self.assertEqual(entry["kind"], WalletActivity.KIND_APP_OPENING)
        self.assertIsNone(entry["txid"])
        self.assertIsNone(entry["amount"])

    def test_activity_outside_date_excluded(self):
        old_day = self.today.replace(year=self.today.year - 1)
        history = self._create_history(txid="old_txid")
        self._create_activity(history=history, day=old_day)
        response = self.client.get(self.url, {"date": self.date_str})
        self.assertEqual(response.json()["count"], 0)

    def test_pagination(self):
        for i in range(5):
            history = self._create_history(txid="tx_%d" % i)
            self._create_activity(history=history)
        response = self.client.get(
            self.url, {"date": self.date_str, "page_size": 2, "page": 1}
        )
        data = response.json()
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["count"], 5)
        self.assertEqual(data["num_pages"], 3)
        self.assertTrue(data["has_next"])

        response = self.client.get(
            self.url, {"date": self.date_str, "page_size": 2, "page": 3}
        )
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertFalse(data["has_next"])

    def test_page_out_of_range_returns_400(self):
        self._create_activity()
        response = self.client.get(
            self.url, {"date": self.date_str, "page": 999}
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_date_returns_400(self):
        response = self.client.get(self.url, {"date": "not-a-date"})
        self.assertEqual(response.status_code, 400)

    def test_non_integer_pagination_returns_400(self):
        response = self.client.get(
            self.url, {"date": self.date_str, "page_size": "abc"}
        )
        self.assertEqual(response.status_code, 400)
