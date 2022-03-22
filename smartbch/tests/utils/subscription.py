import asyncio
from unittest import mock
from django.test import TestCase, tag
from smartbch.tests.mocker import response_values as mock_responses

from django.utils import timezone

from main.models import Subscription
from main.utils import subscription as subscription_utils_main

from smartbch.models import TransactionTransferReceipientLog
from smartbch.utils import subscription as subscription_utils
from smartbch.utils import transaction as transaction_utils


@asyncio.coroutine
def mock_coroutine(*args, **kwargs):
    print("Running mock coroutine")
    return "im_from_a_mock"


class SubscriptionUtilsTestCase(TestCase):
    @mock.patch("web3.eth.Eth.get_transaction_receipt", return_value=mock_responses.test_sep20_transfer_tx_receipt)
    @mock.patch("web3.eth.Eth.get_transaction", return_value=mock_responses.test_sep20_transfer_tx)
    def setUp(self, mock_tx, mock_tx_receipt):
        txid = mock_tx.return_value.hash.hex()

        tx_obj = transaction_utils.save_transaction(txid)
        tx_obj = transaction_utils.save_transaction_transfers(txid)
        tx_transfer_obj = tx_obj.transfers.first()
        address = tx_transfer_obj.from_addr
        telegram_id = 12312

        subscription_utils_main.save_subscription(address, telegram_id)
        self.tx_transfer_obj = tx_transfer_obj

        self.assertTrue(self.tx_transfer_obj.get_valid_subscriptions().exists())
        self.assertTrue(self.tx_transfer_obj.get_unsent_valid_subscriptions().exists())

    @tag("unit")
    @mock.patch("requests.post")
    def test_send_subscription_web_url(self, mock_post_request):
        mock_post_request.return_value.ok = True
        mock_post_request.return_value.status_code = 200

        subscription = self.tx_transfer_obj.get_unsent_valid_subscriptions().first()
        subscription.recipient.telegram_id = None
        subscription.recipient.web_url = "https://example.com/webhook/receiver/"
        subscription.recipient.save()
        subscription.refresh_from_db()

        log, error = subscription_utils.send_transaction_transfer_notification_to_subscriber(
            subscription,
            self.tx_transfer_obj,
        )

        self.assertIsNotNone(log)
        self.assertIsInstance(log, TransactionTransferReceipientLog)
        self.assertIsNotNone(log.sent_at)

    @tag("unit")
    @mock.patch("main.tasks.send_telegram_message", return_value="send notification to 12312")
    def test_send_subscription_telegram(self, mock_send_tg_msg):
        subscription = self.tx_transfer_obj.get_unsent_valid_subscriptions().first()

        log, error = subscription_utils.send_transaction_transfer_notification_to_subscriber(
            subscription,
            self.tx_transfer_obj,
        )

        self.assertIsNotNone(log)
        self.assertIsInstance(log, TransactionTransferReceipientLog)
        self.assertIsNotNone(log.sent_at)

    @tag("unit")
    @mock.patch("channels_redis.core.RedisChannelLayer.group_send", side_effect=mock_coroutine)
    def test_send_subscription_websocket(self, mock_async_to_sync):
        subscription = self.tx_transfer_obj.get_unsent_valid_subscriptions().first()
        subscription.receiver = None
        subscription.websocket = True
        subscription.save()
        subscription.refresh_from_db()

        log, error = subscription_utils.send_transaction_transfer_notification_to_subscriber(
            subscription,
            self.tx_transfer_obj,
        )

        self.assertIsNotNone(log)
        self.assertIsInstance(log, TransactionTransferReceipientLog)
        self.assertIsNotNone(log.sent_at)

    @tag("unit")
    @mock.patch("main.tasks.send_telegram_message", return_value="send notification to 12312")
    def test_send_subscription_prevent_duplicate(self, mock_send_tg_msg):
        subscription = self.tx_transfer_obj.get_unsent_valid_subscriptions().first()

        log, _ = subscription_utils.send_transaction_transfer_notification_to_subscriber(
            subscription,
            self.tx_transfer_obj,
        )

        self.assertIsNotNone(log)
        self.assertIsInstance(log, TransactionTransferReceipientLog)
        self.assertIsNotNone(log.sent_at)

        # test resend if returns the previous log
        log2, _ = subscription_utils.send_transaction_transfer_notification_to_subscriber(
            subscription,
            self.tx_transfer_obj,
        )

        self.assertIsNotNone(log2)
        self.assertIsInstance(log2, TransactionTransferReceipientLog)
        self.assertIsNotNone(log2.sent_at)

        self.assertEqual(log2.id, log.id)

        # checking timestamp if they are sent at the same time due to the implementation
        # using `create_or_update` with only the `sent_at` when logging the send function
        self.assertEqual(log2.sent_at, log.sent_at, "Expected to share timestamp")


class TransactionTransferSubscriptionTestCase(TestCase):
    @mock.patch("web3.eth.Eth.get_transaction_receipt", return_value=mock_responses.test_sep20_transfer_tx_receipt)
    @mock.patch("web3.eth.Eth.get_transaction", return_value=mock_responses.test_sep20_transfer_tx)
    def setUp(self, mock_tx, mock_tx_receipt):
        txid = mock_tx.return_value.hash.hex()

        tx_obj = transaction_utils.save_transaction(txid)
        tx_obj = transaction_utils.save_transaction_transfers(txid)
        tx_transfer_obj = tx_obj.transfers.first()
        address = tx_transfer_obj.from_addr
        telegram_id = 12312

        subscription_utils_main.save_subscription(address, telegram_id)
        self.tx_transfer_obj = tx_transfer_obj

    @tag("unit")
    def test_transaction_transfer_get_subscriptions(self):
        address = self.tx_transfer_obj.from_addr
        subscriptions = self.tx_transfer_obj.get_subscriptions()

        self.assertIsNotNone(
            subscriptions,
            f"Expected subscriptions to return queryset but got None"
        )

        self.assertTrue(
            subscriptions.exists(),
            f"Expected subscriptions queryset to be none empty"
        )

        self.assertEqual(
            subscriptions.first().address.address,
            address,
            f"Expected subscription address to be {address} but got {subscriptions.first().address.address}"
        )

    @tag("unit")
    def test_get_valid_subscriptions(self):
        subscriptions = self.tx_transfer_obj.get_valid_subscriptions()
        subscription = subscriptions.first()
        # 1st part test subscription created is valid
        self.assertIsNotNone(
            subscriptions,
            f"Expected subscriptions to return queryset but got None"
        )
        self.assertTrue(
            subscriptions.exists(),
            f"Expected subscriptions queryset to be none empty"
        )

        # 2nd part set invalid subscription recipient
        subscription.refresh_from_db()
        subscription.recipient.valid = False
        subscription.recipient.save()

        subscriptions = self.tx_transfer_obj.get_valid_subscriptions()
        self.assertIsNotNone(
            subscriptions,
            f"Expected subscriptions to return queryset but got None"
        )
        self.assertFalse(
            subscriptions.exists(),
            f"Expected no subscriptions in queryset but got {subscriptions.count()}"
        )

        # 3rd part no recipient but is websocket
        subscription.refresh_from_db()
        subscription.recipient = None
        subscription.websocket = True
        subscription.save()

        subscriptions = self.tx_transfer_obj.get_valid_subscriptions()
        self.assertIsNotNone(
            subscriptions,
            f"Expected subscriptions to return queryset but got None"
        )
        self.assertTrue(
            subscriptions.exists(),
            f"Expected subscriptions queryset to be none empty"
        )

    @tag("unit")
    def test_get_unsent_valid_subscriptions(self):
        subscriptions = self.tx_transfer_obj.get_unsent_valid_subscriptions()
        subscription = subscriptions.first()
        # 1st part test subscriptions without log instance
        self.assertIsNotNone(
            subscriptions,
            f"Expected subscriptions to return queryset but got None"
        )
        self.assertTrue(
            subscriptions.exists(),
            f"Expected subscriptions queryset to be none empty"
        )

        # 2nd part has log but `sent_at` is null
        TransactionTransferReceipientLog.objects.update_or_create(
            transaction_transfer=self.tx_transfer_obj,
            subscription=subscription,
        )
        subscriptions = self.tx_transfer_obj.get_unsent_valid_subscriptions()
        self.assertIsNotNone(
            subscriptions,
            f"Expected subscriptions to return queryset but got None"
        )
        self.assertTrue(
            subscriptions.exists(),
            f"Expected subscriptions queryset to be none empty"
        )

        # 3rd part has log with `sent_at` set
        TransactionTransferReceipientLog.objects.update_or_create(
            transaction_transfer=self.tx_transfer_obj,
            subscription=subscription,
            defaults={
                "sent_at": timezone.now()
            }
        )

        subscriptions = self.tx_transfer_obj.get_unsent_valid_subscriptions()
        self.assertIsNotNone(
            subscriptions,
            f"Expected subscriptions to return queryset but got None"
        )
        self.assertFalse(
            subscriptions.exists(),
            f"Expected no subscriptions in queryset but got {subscriptions.count()}"
        )

    @tag("unit")
    def test_get_subscription_data(self):
        data = self.tx_transfer_obj.get_subscription_data()
        self.assertIsInstance(data, dict)

        self.assertIn("source", data)
        self.assertIn("txid", data)
        self.assertIn("block_number", data)

        self.assertIn("from", data)
        self.assertIn("to", data)

        self.assertIn("amount", data)
        self.assertIn("token_id", data)
        
        self.assertIn("token_contract", data)
        self.assertIn("address", data["token_contract"])
        self.assertIn("name", data["token_contract"])
        self.assertIn("symbol", data["token_contract"])
