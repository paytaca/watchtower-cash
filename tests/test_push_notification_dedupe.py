"""
Regression tests for duplicate push delivery.

`DeviceWallet` used to be keyed on `(wallet_hash, multi_wallet_index)`, and the
send path grouped devices by that index. Because the index was the wallet's
position in the client's vault list, one wallet accumulated a row per slot it
had ever occupied and every send fanned out once per row — the same
transaction produced one identical notification per row.

These tests pin the replacement behaviour: one subscription per (device,
wallet hash), and one send per wallet hash rather than per vault slot.
"""
import uuid

import pytest
from django.utils import timezone

from notifications.models import DeviceWallet
from notifications.serializers import (
    DeviceSubscriptionSerializer,
    DeviceWalletSerializer,
)
from notifications.utils import send as send_module
from push_notifications.models import APNSDevice, GCMDevice
from push_notifications.models import APNSDeviceQuerySet, GCMDeviceQuerySet


@pytest.fixture
def gcm_device(db):
    return GCMDevice.objects.create(
        name="android",
        registration_id="gcm-registration-id",
        device_id=123456,
        active=True,
        cloud_message_type="FCM",
    )


@pytest.fixture
def apns_device(db):
    return APNSDevice.objects.create(
        name="ios",
        registration_id="apns-registration-id",
        device_id=uuid.uuid4(),
        active=True,
    )


class TestDeviceSubscription:
    def _subscribe(self, device_kind, registration_id, device_id, wallet_hashes):
        serializer = DeviceSubscriptionSerializer(data={
            device_kind: {
                "registration_id": registration_id,
                "device_id": device_id,
                "name": device_kind,
            },
            "wallet_hashes": wallet_hashes,
        })
        serializer.is_valid(raise_exception=True)
        serializer.save()

    def test_repeated_subscribe_does_not_duplicate_rows(self, db, gcm_device):
        for _ in range(3):
            self._subscribe("gcm_device", gcm_device.registration_id, 123456, ["w1", "w2"])

        assert DeviceWallet.objects.filter(gcm_device=gcm_device).count() == 2

    def test_subscribe_keeps_wallets_not_listed(self, db, gcm_device):
        """A client only knows its active wallet, so subscribing to one must not
        unlink the others. An installed app sends the open wallet's hashes on
        every launch and every wallet switch."""
        self._subscribe("gcm_device", gcm_device.registration_id, 123456, ["w1", "w2"])
        self._subscribe("gcm_device", gcm_device.registration_id, 123456, ["w2"])

        assert set(
            DeviceWallet.objects.filter(gcm_device=gcm_device)
            .values_list("wallet_hash", flat=True)
        ) == {"w1", "w2"}

    def test_wallet_switch_does_not_drop_previous_wallet(self, db, gcm_device):
        """Regression: the prune used to be scoped to the submitted wallet set,
        which deleted every vault but the active one."""
        self._subscribe("gcm_device", gcm_device.registration_id, 123456, ["a-bch", "a-slp"])
        self._subscribe("gcm_device", gcm_device.registration_id, 123456, ["b-bch", "b-slp"])

        assert set(
            DeviceWallet.objects.filter(gcm_device=gcm_device)
            .values_list("wallet_hash", flat=True)
        ) == {"a-bch", "a-slp", "b-bch", "b-slp"}

    def test_subscribe_can_opt_in_to_pruning(self, db, gcm_device):
        """A client that really sends its whole set can declare the list
        authoritative and have the rest removed."""
        self._subscribe("gcm_device", gcm_device.registration_id, 123456, ["w1", "w2"])

        serializer = DeviceSubscriptionSerializer(data={
            "gcm_device": {
                "registration_id": gcm_device.registration_id,
                "device_id": 123456,
                "name": "android",
            },
            "wallet_hashes": ["w2"],
            "prune_unlisted": True,
        })
        serializer.is_valid(raise_exception=True)
        serializer.save()

        assert set(
            DeviceWallet.objects.filter(gcm_device=gcm_device)
            .values_list("wallet_hash", flat=True)
        ) == {"w2"}

    def test_prune_unlisted_is_not_leaked_into_serializer_response(self, db, gcm_device):
        """`prune_unlisted` is a write-only directive, not device state."""
        serializer = DeviceSubscriptionSerializer(data={
            "gcm_device": {
                "registration_id": gcm_device.registration_id,
                "device_id": 123456,
                "name": "android",
            },
            "wallet_hashes": ["w1"],
            "prune_unlisted": True,
        })
        serializer.is_valid(raise_exception=True)
        serializer.save()

        assert "prune_unlisted" not in serializer.data
        assert serializer.data["gcm_device"]["id"] == gcm_device.id

    def test_index_field_from_old_clients_is_ignored(self, db, gcm_device):
        """Old app versions still post `multi_wallet_index`; it must not error."""
        serializer = DeviceSubscriptionSerializer(data={
            "gcm_device": {
                "registration_id": gcm_device.registration_id,
                "device_id": 123456,
                "name": "android",
            },
            "wallet_hashes": ["w1"],
            "multi_wallet_index": 4,
        })
        serializer.is_valid(raise_exception=True)
        serializer.save()

        assert DeviceWallet.objects.filter(gcm_device=gcm_device).count() == 1

    def test_device_wallet_serializer_has_no_index(self, db, gcm_device):
        wallet = DeviceWallet.objects.create(
            gcm_device=gcm_device,
            wallet_hash="w1",
            last_active=timezone.now(),
        )
        data = DeviceWalletSerializer(wallet).data

        assert "multi_wallet_index" not in data
        assert data["wallet_hash"] == "w1"


class TestSendFanOut:
    @pytest.fixture
    def sent(self, monkeypatch):
        calls = []

        def fake_send(queryset, message, **kwargs):
            calls.append({
                "model": queryset.model.__name__,
                "count": queryset.count(),
                "extra": kwargs.get("extra"),
                "data": getattr(message, "data", None),
            })
            return [{"success": True}]

        monkeypatch.setattr(GCMDeviceQuerySet, "send_message", fake_send)
        monkeypatch.setattr(APNSDeviceQuerySet, "send_message", fake_send)
        return calls

    def _subscribe(self, device, kind, wallet_hashes):
        DeviceWallet.objects.bulk_create([
            DeviceWallet(**{kind: device}, wallet_hash=wallet_hash, last_active=timezone.now())
            for wallet_hash in wallet_hashes
        ])

    def test_one_send_per_wallet_hash(self, db, gcm_device, sent):
        self._subscribe(gcm_device, "gcm_device", ["w1", "w2"])

        send_module.send_push_notification_to_wallet_hashes(
            ["w1", "w2"], "Received 1 BCH", title="Received",
            extra={"type": send_module.NotificationTypes.MAIN_TRANSACTION},
        )

        assert len(sent) == 2
        assert [call["count"] for call in sent] == [1, 1]
        # `send.py` orders the wallet hashes explicitly, so the send order here
        # is part of the contract rather than a database coincidence.
        assert [call["data"]["wallet_hash"] for call in sent] == ["w1", "w2"]
        # The deprecated field is no longer part of the payload at all.
        assert all("multi_wallet_index" not in call["data"] for call in sent)

    def test_single_wallet_sends_once_even_with_many_devices(self, db, sent):
        first = GCMDevice.objects.create(
            registration_id="gcm-1", device_id=1, active=True, cloud_message_type="FCM",
        )
        second = GCMDevice.objects.create(
            registration_id="gcm-2", device_id=2, active=True, cloud_message_type="FCM",
        )
        self._subscribe(first, "gcm_device", ["w1"])
        self._subscribe(second, "gcm_device", ["w1"])

        send_module.send_push_notification_to_wallet_hashes(
            ["w1"], "Received 1 BCH", title="Received",
            extra={"type": send_module.NotificationTypes.MAIN_TRANSACTION},
        )

        assert len(sent) == 1
        assert sent[0]["count"] == 2

    def test_apns_payload_carries_wallet_hash(self, db, apns_device, sent):
        self._subscribe(apns_device, "apns_device", ["w1"])

        send_module.send_push_notification_to_wallet_hashes(
            ["w1"], "Received 1 BCH", title="Received",
            extra={"type": send_module.NotificationTypes.MAIN_TRANSACTION},
        )

        assert len(sent) == 1
        assert sent[0]["model"] == "APNSDevice"
        assert sent[0]["extra"]["wallet_hash"] == "w1"
        assert sent[0]["extra"]["type"] == send_module.NotificationTypes.MAIN_TRANSACTION

    def test_multiple_wallets_via_serializer_send_once_each(self, db, gcm_device, sent):
        """End-to-end through the subscribe serializer, not just bulk_create.

        The fan-out tests above build rows directly to isolate the send path; this
        one goes through the code the app actually calls, which is also the path
        that enforces the natural key.
        """
        for _ in range(2):
            serializer = DeviceSubscriptionSerializer(data={
                "gcm_device": {
                    "registration_id": gcm_device.registration_id,
                    "device_id": 123456,
                    "name": "android",
                },
                "wallet_hashes": ["w1", "w2", "w3"],
            })
            serializer.is_valid(raise_exception=True)
            serializer.save()

        send_module.send_push_notification_to_wallet_hashes(
            ["w1", "w2", "w3"], "Received 1 BCH", title="Received",
            extra={"type": send_module.NotificationTypes.MAIN_TRANSACTION},
        )

        assert [call["data"]["wallet_hash"] for call in sent] == ["w1", "w2", "w3"]
        assert all(call["count"] == 1 for call in sent)
