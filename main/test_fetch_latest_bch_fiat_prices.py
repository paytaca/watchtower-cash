from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import requests
from django.test import TestCase

from main.models import AssetPriceLog
from main.tasks import fetch_latest_bch_fiat_prices


QUOTE_TIME = datetime(2026, 11, 4, 6, 20, tzinfo=timezone.utc)


class FetchLatestBchFiatPricesTest(TestCase):
    def setUp(self):
        patcher = patch("rampp2p.models.FiatCurrency")
        self.fiat_currency_model = patcher.start()
        self.addCleanup(patcher.stop)
        self.fiat_currency_model.objects.all.return_value.values_list.return_value = []

    @patch("main.tasks.get_latest_bch_rates")
    def test_stores_currency_resolved_through_yadio(self, get_rates):
        get_rates.return_value = {
            "usd": (Decimal("612.40"), QUOTE_TIME, "coingecko"),
            "aud": (Decimal("933.02"), QUOTE_TIME, "coingecko-yadio"),
        }

        results = fetch_latest_bch_fiat_prices(currencies=["USD", "AUD"])

        get_rates.assert_called_once_with(currencies=["USD", "AUD"])
        aud = AssetPriceLog.objects.get(currency="AUD", relative_currency="BCH")
        self.assertEqual(aud.price_value, Decimal("933.02"))
        self.assertEqual(aud.source, "coingecko-yadio")
        self.assertEqual(aud.timestamp, QUOTE_TIME)
        self.assertEqual({row["currency"] for row in results}, {"USD", "AUD"})

    @patch("main.tasks.get_latest_bch_rates")
    def test_stores_coingecko_currency(self, get_rates):
        get_rates.return_value = {
            "usd": (Decimal("612.40"), QUOTE_TIME, "coingecko"),
        }

        fetch_latest_bch_fiat_prices(currencies=["USD"])

        usd = AssetPriceLog.objects.get(currency="USD", relative_currency="BCH")
        self.assertEqual(usd.price_value, Decimal("612.40"))
        self.assertEqual(usd.source, "coingecko")

    @patch("main.tasks.get_latest_bch_rates")
    def test_stores_ars_with_yadio_source(self, get_rates):
        get_rates.return_value = {
            "ars": (Decimal("916800.00"), QUOTE_TIME, "coingecko-yadio"),
        }

        fetch_latest_bch_fiat_prices(currencies=["ARS"])

        ars = AssetPriceLog.objects.get(currency="ARS", relative_currency="BCH")
        self.assertEqual(ars.price_value, Decimal("916800.00"))
        self.assertEqual(ars.source, "coingecko-yadio")

    @patch("main.tasks.get_latest_bch_rates")
    def test_skips_currencies_without_a_rate(self, get_rates):
        get_rates.return_value = {
            "usd": (Decimal("612.40"), QUOTE_TIME, "coingecko"),
        }

        results = fetch_latest_bch_fiat_prices(currencies=["USD", "XYZ"])

        self.assertFalse(AssetPriceLog.objects.filter(currency="XYZ").exists())
        self.assertEqual([row["currency"] for row in results], ["USD"])

    @patch("main.tasks.get_latest_bch_rates")
    def test_unions_rampp2p_currencies(self, get_rates):
        self.fiat_currency_model.objects.all.return_value.values_list.return_value = [
            "eur",
        ]
        get_rates.return_value = {}

        fetch_latest_bch_fiat_prices(currencies=["USD"])

        get_rates.assert_called_once_with(currencies=["USD", "EUR"])

    @patch("main.tasks.get_latest_bch_rates")
    def test_accepts_comma_separated_currencies(self, get_rates):
        get_rates.return_value = {}

        fetch_latest_bch_fiat_prices(currencies="usd, aud")

        get_rates.assert_called_once_with(currencies=["USD", "AUD"])

    @patch("main.tasks.get_latest_bch_rates")
    def test_updates_existing_price_log(self, get_rates):
        AssetPriceLog.objects.create(
            currency="AUD",
            relative_currency="BCH",
            timestamp=QUOTE_TIME,
            source="coingecko-yadio",
            price_value=Decimal("900.00"),
        )
        get_rates.return_value = {
            "aud": (Decimal("933.02"), QUOTE_TIME, "coingecko-yadio"),
        }

        fetch_latest_bch_fiat_prices(currencies=["AUD"])

        self.assertEqual(AssetPriceLog.objects.filter(currency="AUD").count(), 1)
        aud = AssetPriceLog.objects.get(currency="AUD", relative_currency="BCH")
        self.assertEqual(aud.price_value, Decimal("933.02"))

    @patch("main.tasks.get_latest_bch_rates")
    def test_propagates_upstream_failure(self, get_rates):
        get_rates.side_effect = requests.RequestException("boom")

        with self.assertRaises(requests.RequestException):
            fetch_latest_bch_fiat_prices(currencies=["USD"])

        self.assertFalse(AssetPriceLog.objects.exists())
