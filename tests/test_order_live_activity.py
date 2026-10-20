"""
Unit tests for P2P Ramp order live activities.

Covers the parts most likely to regress silently (a renamed status code dropping
out of the stage map, terminal semantics, masked payloads) plus the delivery and
registration-pruning rules, with all push transports mocked out. No APNs/FCM
credentials are needed.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from django.db import transaction
from django.utils import timezone
from firebase_admin import messaging

from notifications.models import OrderLiveActivityToken
from notifications.serializers import OrderLiveActivitySerializer
from notifications.tasks import push_order_live_activity
from notifications.utils import live_activity as delivery
from rampp2p import models
from rampp2p.utils import live_activity as activity_builder


# --------------------------------------------------------------------------
# build_order_live_activity
# --------------------------------------------------------------------------

class TestBuildOrderLiveActivity:
    def _order(self, **overrides):
        order = SimpleNamespace(
            id=42,
            trade_type="SELL",
            expires_at=None,
            status=None,
        )
        for key, value in overrides.items():
            setattr(order, key, value)
        return order

    def test_all_status_codes_are_mapped(self):
        """Every order status must appear in the stage map (catches renames)."""
        status_codes = {code for code, _ in models.StatusType.choices}
        mapped = set(activity_builder.P2P_STAGE_INDEX)
        assert mapped - status_codes == set(), (
            f"P2P_STAGE_INDEX has codes that are no longer order statuses: "
            f"{sorted(mapped - status_codes)}"
        )
        assert status_codes - mapped == set(), (
            f"Order statuses missing from P2P_STAGE_INDEX: "
            f"{sorted(status_codes - mapped)}"
        )

    def test_terminal_codes_are_real_statuses(self):
        terminal = set(activity_builder.P2P_TERMINAL)
        status_codes = {code for code, _ in models.StatusType.choices}
        assert terminal <= status_codes
        # A terminal status must never also be a mid-flow stage.
        assert terminal == {"RLS", "RFN", "CNCL"}

    def test_stage_index_and_progress(self):
        order = self._order()
        activity = activity_builder.build_order_live_activity(
            order, SimpleNamespace(status="ESCRW")
        )
        assert activity["statusCode"] == "ESCRW"
        assert activity["stageIndex"] == activity_builder.P2P_STAGE_INDEX["ESCRW"]
        assert activity["stageCount"] == activity_builder.P2P_STAGE_COUNT
        assert activity["progress"] == round(
            activity_builder.P2P_STAGE_INDEX["ESCRW"]
            / activity_builder.P2P_STAGE_COUNT,
            2,
        )
        assert activity["isTerminal"] is False
        assert activity["terminalType"] is None

    @pytest.mark.parametrize(
        "code,terminal_type",
        [("RLS", "success"), ("RFN", "failed"), ("CNCL", "cancelled")],
    )
    def test_terminal_mapping(self, code, terminal_type):
        activity = activity_builder.build_order_live_activity(
            self._order(), SimpleNamespace(status=code)
        )
        assert activity["isTerminal"] is True
        assert activity["terminalType"] == terminal_type
        assert activity["statusCode"] == code

    def test_lowercase_status_is_normalized(self):
        activity = activity_builder.build_order_live_activity(
            self._order(), SimpleNamespace(status="cnf")
        )
        assert activity["statusCode"] == "CNF"
        assert activity["stageIndex"] == activity_builder.P2P_STAGE_INDEX["CNF"]

    def test_unknown_status_falls_back_without_terminal(self):
        activity = activity_builder.build_order_live_activity(
            self._order(), SimpleNamespace(status="NOPE")
        )
        assert activity["stageIndex"] == 0
        assert activity["progress"] == 0.0
        assert activity["isTerminal"] is False

    def test_payload_is_masked(self):
        """No amounts, counterparty names or addresses may leak to the lock screen."""
        order = self._order(trade_type="SELL", expires_at=timezone.now())
        activity = activity_builder.build_order_live_activity(
            order, SimpleNamespace(status="PD")
        )
        allowed_keys = {
            "id", "kind", "orderId", "title", "subtitle", "statusCode",
            "statusLabel", "stageIndex", "stageCount", "progress",
            "countdownAt", "countdownLabel", "isTerminal", "terminalType",
            "deepLink", "updatedAt",
        }
        assert set(activity) == allowed_keys
        assert activity["subtitle"] == "Order #42 \u00b7 Sell"
        # A participant name must never be part of the payload.
        order.owner = SimpleNamespace(name="Alice", wallet_hash="abc")
        after = activity_builder.build_order_live_activity(
            order, SimpleNamespace(status="PD")
        )
        assert "Alice" not in str(after)

    def test_countdown_present_only_for_live_orders(self):
        expires_at = timezone.now() + timedelta(minutes=30)
        live = activity_builder.build_order_live_activity(
            self._order(expires_at=expires_at), SimpleNamespace(status="PD")
        )
        assert live["countdownAt"] == int(expires_at.timestamp() * 1000)

        done = activity_builder.build_order_live_activity(
            self._order(expires_at=expires_at), SimpleNamespace(status="RLS")
        )
        assert done["countdownAt"] is None

    def test_epoch_ms(self):
        assert activity_builder._epoch_ms(None) is None
        when = timezone.now()
        assert activity_builder._epoch_ms(when) == int(when.timestamp() * 1000)
        # The unix epoch is a real timestamp (0), not "missing".
        assert activity_builder._epoch_ms(datetime(1970, 1, 1, tzinfo=timezone.utc)) == 0

    def test_status_defaults_to_order_status_when_not_passed(self):
        order = self._order(status=SimpleNamespace(status="SBM"))
        activity = activity_builder.build_order_live_activity(order)
        assert activity["statusCode"] == "SBM"


# --------------------------------------------------------------------------
# is_order_member
# --------------------------------------------------------------------------

class TestIsOrderMember:
    def _order(self):
        return SimpleNamespace(
            is_seller=lambda wallet_hash: wallet_hash == "seller_hash",
            is_buyer=lambda wallet_hash: wallet_hash == "buyer_hash",
            arbiter_id=7,
            arbiter=SimpleNamespace(wallet_hash="arbiter_hash"),
        )

    def test_seller_and_buyer(self):
        assert activity_builder.is_order_member(self._order(), "seller_hash")
        assert activity_builder.is_order_member(self._order(), "buyer_hash")

    def test_arbiter(self):
        assert activity_builder.is_order_member(self._order(), "arbiter_hash")

    def test_non_member(self):
        assert not activity_builder.is_order_member(self._order(), "stranger")

    def test_missing_wallet_hash(self):
        assert not activity_builder.is_order_member(self._order(), None)
        assert not activity_builder.is_order_member(self._order(), "")

    def test_no_arbiter(self):
        order = self._order()
        order.arbiter_id = None
        order.arbiter = None
        assert not activity_builder.is_order_member(order, "arbiter_hash")

    def test_membership_check_errors_do_not_grant_access(self):
        def boom(wallet_hash):
            raise ValueError("broken ad snapshot")

        order = SimpleNamespace(
            is_seller=boom, is_buyer=boom, arbiter_id=None, arbiter=None,
        )
        assert not activity_builder.is_order_member(order, "seller_hash")


# --------------------------------------------------------------------------
# OrderLiveActivitySerializer start/update/end semantics
# --------------------------------------------------------------------------

@pytest.mark.django_db
class TestOrderLiveActivitySerializer:
    def _register(self, action, token="tok-1"):
        serializer = OrderLiveActivitySerializer(
            data={
                "order_id": 1,
                "token": token,
                "type": action,
                "platform": OrderLiveActivityToken.Platform.IOS,
            }
        )
        serializer.is_valid(raise_exception=True)
        return serializer.save()

    def test_start_registers(self):
        result = self._register("start")
        assert result["registered"] is True
        assert OrderLiveActivityToken.objects.filter(token="tok-1").count() == 1

    def test_update_is_idempotent(self):
        first = self._register("start")
        second = self._register("update")
        assert second["id"] == first["id"]
        assert OrderLiveActivityToken.objects.count() == 1

    def test_end_removes_registration(self):
        self._register("start")
        result = self._register("end")
        assert result["registered"] is False
        assert not OrderLiveActivityToken.objects.filter(token="tok-1").exists()

    def test_end_is_idempotent(self):
        result = self._register("end")
        assert result["registered"] is False
        assert OrderLiveActivityToken.objects.count() == 0

    def test_end_only_removes_the_matching_platform(self):
        OrderLiveActivityToken.objects.create(
            order_id=1,
            token="tok-1",
            platform=OrderLiveActivityToken.Platform.ANDROID,
        )
        self._register("end")
        assert OrderLiveActivityToken.objects.filter(
            platform=OrderLiveActivityToken.Platform.ANDROID
        ).exists()

    def test_invalid_action_rejected(self):
        serializer = OrderLiveActivitySerializer(
            data={
                "order_id": 1,
                "token": "tok-1",
                "type": "resume",
                "platform": OrderLiveActivityToken.Platform.IOS,
            }
        )
        assert not serializer.is_valid()
        assert "type" in serializer.errors


# --------------------------------------------------------------------------
# APNs payload + delivery/pruning rules
# --------------------------------------------------------------------------

def _activity(is_terminal=False):
    return {
        "id": "p2p:1",
        "statusCode": "RLS" if is_terminal else "PD",
        "isTerminal": is_terminal,
    }


@pytest.fixture
def order_tokens(db):
    """Two iOS and two Android registrations for order 1."""
    return {
        "ios_1": OrderLiveActivityToken.objects.create(
            order_id=1, token="ios-token-1", platform="ios"
        ),
        "ios_2": OrderLiveActivityToken.objects.create(
            order_id=1, token="ios-token-2", platform="ios"
        ),
        "android_1": OrderLiveActivityToken.objects.create(
            order_id=1, token="android-token-1", platform="android"
        ),
        "android_2": OrderLiveActivityToken.objects.create(
            order_id=1, token="android-token-2", platform="android"
        ),
    }


def _fcm_response(success=True, exception=None):
    return messaging.SendResponse({"name": "projects/x/messages/1"} if success else None,
                                  exception)


class TestFcmBatch:
    def test_batch_response_is_unwrapped(self, mocker):
        """`send_each` returns a BatchResponse, not a list; the caller expects
        one SendResponse per message."""
        first, second = _fcm_response(), _fcm_response()
        send_each = mocker.patch.object(
            messaging, "send_each",
            return_value=messaging.BatchResponse([first, second]),
        )
        mocker.patch.object(delivery, "get_manager")

        messages = [object(), object()]
        responses = delivery.send_live_activity_fcm_batch(messages)

        assert send_each.call_count == 1
        assert responses == [first, second]

    def test_empty_batch_skips_the_api(self, mocker):
        send_each = mocker.patch.object(messaging, "send_each")

        assert delivery.send_live_activity_fcm_batch([]) == []
        assert not send_each.called


class TestApnsPayload:
    def test_update_uses_stale_date(self):
        aps = delivery.build_apns_aps(_activity(), event="update")
        assert aps["event"] == "update"
        assert "stale-date" in aps
        assert "dismissal-date" not in aps

    def test_end_uses_dismissal_date(self):
        aps = delivery.build_apns_aps(_activity(True), event="end")
        assert aps["event"] == "end"
        assert "dismissal-date" in aps
        assert "stale-date" not in aps

    def test_content_state_carries_every_expected_key(self):
        activity = activity_builder.build_order_live_activity(
            SimpleNamespace(id=1, trade_type="BUY", expires_at=None, status=None),
            SimpleNamespace(status="PD"),
        )
        content_state = delivery.build_apns_aps(activity)["content-state"]
        assert set(content_state) == set(delivery.CONTENT_STATE_KEYS)
        assert content_state["statusCode"] == "PD"


@pytest.mark.django_db
class TestSendOrderLiveActivity:
    def test_ios_tokens_share_one_apns_batch(self, order_tokens, mocker):
        batch = mocker.patch.object(
            delivery, "send_live_activity_apns_batch",
            return_value={"ios-token-1": "Success", "ios-token-2": "Success"},
        )
        mocker.patch.object(delivery, "_apns_client")

        delivery.send_order_live_activity(
            _activity(), OrderLiveActivityToken.objects.filter(order_id=1)
        )

        assert batch.call_count == 1
        sent_tokens = set(batch.call_args[0][0])
        assert sent_tokens == {"ios-token-1", "ios-token-2"}

    def test_android_tokens_share_one_fcm_batch(self, order_tokens, mocker):
        batch = mocker.patch.object(
            delivery, "send_live_activity_fcm_batch",
            return_value=[_fcm_response(), _fcm_response()],
        )
        mocker.patch.object(delivery, "send_live_activity_apns_batch", return_value={})

        delivery.send_order_live_activity(
            _activity(), OrderLiveActivityToken.objects.filter(order_id=1)
        )

        assert batch.call_count == 1
        messages = batch.call_args[0][0]
        assert len(messages) == 2
        assert {message.token for message in messages} == {
            "android-token-1", "android-token-2",
        }

    def test_update_keeps_registrations(self, order_tokens, mocker):
        mocker.patch.object(
            delivery, "send_live_activity_apns_batch",
            return_value={"ios-token-1": "Success", "ios-token-2": "Success"},
        )
        mocker.patch.object(
            delivery, "send_live_activity_fcm_batch",
            return_value=[_fcm_response(), _fcm_response()],
        )

        delivery.send_order_live_activity(
            _activity(), OrderLiveActivityToken.objects.filter(order_id=1)
        )

        assert OrderLiveActivityToken.objects.count() == 4

    def test_terminal_push_prunes_delivered_registrations(self, order_tokens, mocker):
        mocker.patch.object(
            delivery, "send_live_activity_apns_batch",
            return_value={"ios-token-1": "Success", "ios-token-2": "Success"},
        )
        mocker.patch.object(
            delivery, "send_live_activity_fcm_batch",
            return_value=[_fcm_response(), _fcm_response()],
        )

        delivery.send_order_live_activity(
            _activity(True), OrderLiveActivityToken.objects.filter(order_id=1)
        )

        assert OrderLiveActivityToken.objects.count() == 0

    def test_failed_apns_end_keeps_registration(self, order_tokens, mocker):
        """A failed terminal push must be retryable, not silently forgotten."""
        mocker.patch.object(
            delivery, "send_live_activity_apns_batch",
            return_value={"ios-token-1": "Success", "ios-token-2": "BadDeviceToken"},
        )
        mocker.patch.object(
            delivery, "send_live_activity_fcm_batch",
            return_value=[_fcm_response(), _fcm_response()],
        )

        delivery.send_order_live_activity(
            _activity(True), OrderLiveActivityToken.objects.filter(order_id=1)
        )

        remaining = set(
            OrderLiveActivityToken.objects.values_list(
                "platform", "token"
            )
        )
        assert remaining == {("ios", "ios-token-2")}

    def test_unregistered_ios_token_is_pruned(self, order_tokens, mocker):
        mocker.patch.object(
            delivery, "send_live_activity_apns_batch",
            return_value={
                "ios-token-1": "Success",
                "ios-token-2": ("Unregistered", "1700000000"),
            },
        )
        mocker.patch.object(
            delivery, "send_live_activity_fcm_batch",
            return_value=[_fcm_response(), _fcm_response()],
        )

        delivery.send_order_live_activity(
            _activity(), OrderLiveActivityToken.objects.filter(order_id=1)
        )

        assert not OrderLiveActivityToken.objects.filter(token="ios-token-2").exists()
        assert OrderLiveActivityToken.objects.filter(token="ios-token-1").exists()

    @pytest.mark.parametrize(
        "reason",
        ["BadTopic", "InvalidProviderToken", "TopicDisallowed", "MissingTopic"],
    )
    def test_apns_configuration_errors_are_logged_as_errors(
        self, order_tokens, mocker, reason
    ):
        """A deployment-level APNs failure must not be swallowed."""
        mocker.patch.object(
            delivery, "send_live_activity_apns_batch",
            return_value={"ios-token-1": reason, "ios-token-2": "Success"},
        )
        mocker.patch.object(
            delivery, "send_live_activity_fcm_batch",
            return_value=[_fcm_response(), _fcm_response()],
        )
        error_log = mocker.patch.object(delivery.LOGGER, "error")
        warning_log = mocker.patch.object(delivery.LOGGER, "warning")

        delivery.send_order_live_activity(
            _activity(), OrderLiveActivityToken.objects.filter(order_id=1)
        )

        assert error_log.call_count == 1
        message = error_log.call_args[0][0]
        assert reason in message
        # The operator needs to know which knob to check.
        assert "LIVE_ACTIVITY_APNS_TOPIC" in message
        assert not warning_log.called

    def test_apns_device_errors_are_logged_as_warnings(
        self, order_tokens, mocker
    ):
        """A single bad token is a warning, not a deployment error."""
        mocker.patch.object(
            delivery, "send_live_activity_apns_batch",
            return_value={"ios-token-1": "BadDeviceToken", "ios-token-2": "Success"},
        )
        mocker.patch.object(
            delivery, "send_live_activity_fcm_batch",
            return_value=[_fcm_response(), _fcm_response()],
        )
        error_log = mocker.patch.object(delivery.LOGGER, "error")
        warning_log = mocker.patch.object(delivery.LOGGER, "warning")

        delivery.send_order_live_activity(
            _activity(), OrderLiveActivityToken.objects.filter(order_id=1)
        )

        assert warning_log.call_count == 1
        assert "BadDeviceToken" in warning_log.call_args[0][0]
        assert not error_log.called

    def test_unregistered_fcm_token_is_pruned_by_type(self, order_tokens, mocker):
        mocker.patch.object(delivery, "send_live_activity_apns_batch", return_value={})
        mocker.patch.object(
            delivery, "send_live_activity_fcm_batch",
            return_value=[
                _fcm_response(success=False, exception=messaging.UnregisteredError("stale")),
                _fcm_response(),
            ],
        )

        delivery.send_order_live_activity(
            _activity(), OrderLiveActivityToken.objects.filter(order_id=1)
        )

        assert not OrderLiveActivityToken.objects.filter(
            token="android-token-1"
        ).exists()
        assert OrderLiveActivityToken.objects.filter(token="android-token-2").exists()

    def test_generic_fcm_failure_keeps_registration(self, order_tokens, mocker):
        mocker.patch.object(delivery, "send_live_activity_apns_batch", return_value={})
        mocker.patch.object(
            delivery, "send_live_activity_fcm_batch",
            return_value=[
                _fcm_response(success=False, exception=messaging.QuotaExceededError("quota")),
                _fcm_response(),
            ],
        )

        delivery.send_order_live_activity(
            _activity(), OrderLiveActivityToken.objects.filter(order_id=1)
        )

        assert OrderLiveActivityToken.objects.filter(
            token="android-token-1"
        ).exists()

    def test_apns_connection_failure_does_not_block_android(
        self, order_tokens, mocker
    ):
        mocker.patch.object(
            delivery, "send_live_activity_apns_batch",
            side_effect=ConnectionError("apns down"),
        )
        fcm = mocker.patch.object(
            delivery, "send_live_activity_fcm_batch",
            return_value=[_fcm_response(), _fcm_response()],
        )

        delivery.send_order_live_activity(
            _activity(), OrderLiveActivityToken.objects.filter(order_id=1)
        )

        assert fcm.called
        # iOS registrations survive a transport failure.
        assert OrderLiveActivityToken.objects.filter(platform="ios").count() == 2

    def test_no_tokens_is_a_noop(self, db, mocker):
        apns = mocker.patch.object(delivery, "send_live_activity_apns_batch")
        fcm = mocker.patch.object(delivery, "send_live_activity_fcm_batch")

        assert delivery.send_order_live_activity(_activity(), []) == []
        assert not apns.called
        assert not fcm.called

    def test_batch_prunes_exact_tokens_only(self, order_tokens, mocker):
        """A failing token in a batch must not prune the other order's tokens."""
        other = OrderLiveActivityToken.objects.create(
            order_id=2, token="ios-other", platform="ios"
        )
        mocker.patch.object(
            delivery, "send_live_activity_apns_batch",
            return_value={"ios-token-1": "Success", "ios-token-2": "Success"},
        )
        mocker.patch.object(
            delivery, "send_live_activity_fcm_batch",
            return_value=[_fcm_response(), _fcm_response()],
        )

        delivery.send_order_live_activity(
            _activity(True), OrderLiveActivityToken.objects.filter(order_id=1)
        )

        assert OrderLiveActivityToken.objects.filter(pk=other.pk).exists()

    def test_topic_uses_configured_base(self, settings):
        settings.LIVE_ACTIVITY_APNS_TOPIC = "com.example.other"
        assert (
            delivery.get_live_activity_apns_topic()
            == "com.example.other.push-type.liveactivity"
        )


# --------------------------------------------------------------------------
# Signal -> task handoff
# --------------------------------------------------------------------------

@pytest.mark.django_db
class TestOrderLiveActivityDispatch:
    def test_no_registrations_means_no_task(self, db, mocker):
        task = mocker.patch("notifications.tasks.push_order_live_activity.delay")
        order = SimpleNamespace(id=999, trade_type="SELL", expires_at=None)

        queued = activity_builder.update_order_live_activity(
            order, SimpleNamespace(status="SBM")
        )

        assert queued is False
        assert not task.called

    def test_task_queued_with_registration_ids(
        self, order_tokens, mocker, django_capture_on_commit_callbacks
    ):
        task = mocker.patch("notifications.tasks.push_order_live_activity.delay")
        order = SimpleNamespace(id=1, trade_type="SELL", expires_at=None)

        # The push is deferred to commit; run the callbacks like a committed txn.
        with django_capture_on_commit_callbacks(execute=True):
            queued = activity_builder.update_order_live_activity(
                order, SimpleNamespace(status="PD")
            )

        assert queued is True
        assert task.called
        activity, token_ids = task.call_args[0]
        assert activity["statusCode"] == "PD"
        assert sorted(token_ids) == sorted(
            OrderLiveActivityToken.objects.filter(order_id=1).values_list(
                "id", flat=True
            )
        )

    def test_rolled_back_transaction_does_not_queue(
        self, order_tokens, mocker, django_capture_on_commit_callbacks
    ):
        """A status change that never commits must not reach the devices."""
        task = mocker.patch("notifications.tasks.push_order_live_activity.delay")
        order = SimpleNamespace(id=1, trade_type="SELL", expires_at=None)

        with django_capture_on_commit_callbacks(execute=False):
            with pytest.raises(RuntimeError):
                with transaction.atomic():
                    activity_builder.update_order_live_activity(
                        order, SimpleNamespace(status="PD")
                    )
                    raise RuntimeError("status save failed")

        assert not task.called

    def test_broker_failure_does_not_raise(
        self, order_tokens, mocker, django_capture_on_commit_callbacks
    ):
        """The status change is already committed; a dead broker must not 500."""
        task = mocker.patch(
            "notifications.tasks.push_order_live_activity.delay",
            side_effect=ConnectionError("broker down"),
        )
        order = SimpleNamespace(id=1, trade_type="SELL", expires_at=None)

        with django_capture_on_commit_callbacks(execute=True):
            queued = activity_builder.update_order_live_activity(
                order, SimpleNamespace(status="PD")
            )

        assert queued is True
        assert task.called


# --------------------------------------------------------------------------
# Celery task
# --------------------------------------------------------------------------

@pytest.mark.django_db
class TestPushOrderLiveActivityTask:
    def test_delivers_to_the_given_registrations(self, order_tokens, mocker):
        send = mocker.patch.object(
            delivery, "send_order_live_activity", return_value=[]
        )

        push_order_live_activity(_activity(), [order_tokens["ios_1"].pk])

        assert send.call_count == 1
        activity, tokens = send.call_args[0]
        assert activity == _activity()
        assert [token.pk for token in tokens] == [order_tokens["ios_1"].pk]

    def test_skips_registrations_removed_before_it_runs(self, order_tokens, mocker):
        """Ending an activity from the app may delete the row before the task runs."""
        apns = mocker.patch.object(delivery, "send_live_activity_apns_batch")
        fcm = mocker.patch.object(delivery, "send_live_activity_fcm_batch")
        stale_id = order_tokens["ios_1"].pk
        OrderLiveActivityToken.objects.filter(pk=stale_id).delete()

        assert push_order_live_activity(_activity(), [stale_id]) == []

        # The stale id is simply not there any more; no transport is touched.
        assert not apns.called
        assert not fcm.called

    def test_tolerates_a_missing_token_list(self, db, mocker):
        send = mocker.patch.object(delivery, "send_order_live_activity", return_value=[])

        push_order_live_activity(_activity(), None)

        assert list(send.call_args[0][1]) == []
