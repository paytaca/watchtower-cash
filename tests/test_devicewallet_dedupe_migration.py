"""
Tests for the `multi_wallet_index` drop migration's de-duplication step.

The de-duplication runs before the unique constraints are added, so a bug here
makes the migration itself fail on real data — not something that surfaces in
the send path first. These tests call the migration's function directly against
real models, one row-shape at a time.

Duplicates cannot be inserted while the constraints exist, so each test drops
them first and restores them afterwards. That mirrors the real migration, which
runs on a table that does not have the constraints yet.

Wallet hashes are namespaced per test so the assertions never depend on whatever
else the suite's fixtures loaded.
"""
import importlib
import uuid
from datetime import timedelta

import pytest
from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from notifications.models import DeviceWallet
from push_notifications.models import APNSDevice, GCMDevice

# The module name starts with a digit, so it cannot be reached with `from ...
# import`; importlib takes the name as a plain string.
migration_module = importlib.import_module(
    "notifications.migrations.0004_dedupe_devicewallet_and_drop_multi_wallet_index"
)
dedupe_device_wallets = migration_module.dedupe_device_wallets

# SQLite rebuilds the whole table to change constraints, and its schema editor
# refuses to run inside a transaction. `transaction=True` keeps each test in
# autocommit so the fixture can restructure the table.
pytestmark = pytest.mark.django_db(transaction=True)


def _set_constraints(constraints):
    """Rewrite the table so it has exactly `constraints` on DeviceWallet."""
    existing = DeviceWallet._meta.constraints
    DeviceWallet._meta.constraints = list(constraints)
    with connection.schema_editor() as editor:
        if connection.vendor == "sqlite":
            editor._remake_table(DeviceWallet)
        else:
            for constraint in constraints:
                if constraint not in existing:
                    editor.add_constraint(DeviceWallet, constraint)
            for constraint in existing:
                if constraint not in constraints:
                    editor.remove_constraint(DeviceWallet, constraint)


@pytest.fixture
def without_constraints():
    """Run the body against a table shaped like it was before the constraints.

    The test database is built from the models, so the unique constraints are
    already in place and duplicate rows cannot be inserted. The migration runs
    against a table that does not have them yet, so the body needs the same
    shape.
    """
    constraints = list(DeviceWallet._meta.constraints)
    _set_constraints([])
    try:
        yield
    finally:
        _set_constraints(constraints)


@pytest.fixture
def gcm():
    return GCMDevice.objects.create(
        name="android",
        registration_id=f"gcm-{uuid.uuid4()}",
        device_id=uuid.uuid4().int % (2 ** 63),
        active=True,
        cloud_message_type="FCM",
    )


@pytest.fixture
def apns():
    return APNSDevice.objects.create(
        name="ios",
        registration_id=f"apns-{uuid.uuid4()}",
        device_id=uuid.uuid4(),
        active=True,
    )


def _wallets(wallet_hash):
    return DeviceWallet.objects.filter(wallet_hash=wallet_hash)


class TestDedupe:
    def test_keeps_only_the_most_recent_gcm_row(self, without_constraints, gcm):
        wallet_hash = f"dedupe-{uuid.uuid4()}"
        now = timezone.now()
        for days_ago in (3, 1, 2):
            DeviceWallet.objects.create(
                gcm_device=gcm,
                wallet_hash=wallet_hash,
                last_active=now - timedelta(days=days_ago),
            )

        dedupe_device_wallets(apps, None)

        rows = list(_wallets(wallet_hash).values_list("gcm_device_id", "last_active"))
        assert len(rows) == 1
        assert rows[0][1] == now - timedelta(days=1)

    def test_duplicates_that_only_reference_one_device_are_deleted(
        self, without_constraints, gcm,
    ):
        """A duplicate that only referenced a GCM device has nothing left to link."""
        wallet_hash = f"dedupe-{uuid.uuid4()}"
        DeviceWallet.objects.create(gcm_device=gcm, wallet_hash=wallet_hash, last_active=timezone.now())
        DeviceWallet.objects.create(gcm_device=gcm, wallet_hash=wallet_hash, last_active=timezone.now())

        dedupe_device_wallets(apps, None)

        rows = list(_wallets(wallet_hash).values_list("gcm_device_id", "apns_device_id"))
        assert rows == [(gcm.id, None)]

    def test_dual_fk_duplicate_is_unlinked_not_deleted(
        self, without_constraints, gcm, apns,
    ):
        """A dual-FK row colliding on both sides must keep both surviving links.

        This is the case that makes the two-pass ordering matter: deleting the
        dual row in the GCM pass would also drop the APNs device's only link to
        the wallet, so the row is unlinked instead and the APNs pass then
        resolves the other side independently.
        """
        wallet_hash = f"dedupe-{uuid.uuid4()}"
        now = timezone.now()
        DeviceWallet.objects.create(gcm_device=gcm, wallet_hash=wallet_hash, last_active=now)
        DeviceWallet.objects.create(apns_device=apns, wallet_hash=wallet_hash, last_active=now)
        DeviceWallet.objects.create(
            gcm_device=gcm, apns_device=apns, wallet_hash=wallet_hash,
            last_active=now - timedelta(days=1),
        )

        dedupe_device_wallets(apps, None)

        rows = list(
            _wallets(wallet_hash).values_list("gcm_device_id", "apns_device_id")
        )
        # One row per device, and the APNs link survives the GCM pass.
        assert len(rows) == 2
        assert (gcm.id, None) in rows
        assert (None, apns.id) in rows

    def test_preexisting_all_null_orphan_is_left_alone(self, without_constraints):
        """Rows with no device cannot deliver a push; the migration does not guess."""
        wallet_hash = f"dedupe-{uuid.uuid4()}"
        DeviceWallet.objects.create(
            gcm_device=None, apns_device=None, wallet_hash=wallet_hash,
            last_active=timezone.now(),
        )

        dedupe_device_wallets(apps, None)

        rows = list(_wallets(wallet_hash).values_list("gcm_device_id", "apns_device_id"))
        assert rows == [(None, None)]

    def test_distinct_wallets_are_untouched(self, without_constraints, gcm):
        now = timezone.now()
        hashes = [f"dedupe-{uuid.uuid4()}" for _ in range(3)]
        for wallet_hash in hashes:
            DeviceWallet.objects.create(gcm_device=gcm, wallet_hash=wallet_hash, last_active=now)

        dedupe_device_wallets(apps, None)

        for wallet_hash in hashes:
            assert _wallets(wallet_hash).count() == 1


class TestConstraints:
    def test_duplicate_gcm_link_is_rejected(self, gcm):
        wallet_hash = f"dedupe-{uuid.uuid4()}"
        DeviceWallet.objects.create(gcm_device=gcm, wallet_hash=wallet_hash, last_active=timezone.now())

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                DeviceWallet.objects.create(
                    gcm_device=gcm, wallet_hash=wallet_hash, last_active=timezone.now(),
                )

    def test_gcm_and_apns_rows_for_one_wallet_coexist(self, gcm, apns):
        """NULLs being distinct is what lets a wallet have one link per device type."""
        wallet_hash = f"dedupe-{uuid.uuid4()}"

        DeviceWallet.objects.create(gcm_device=gcm, wallet_hash=wallet_hash, last_active=timezone.now())
        DeviceWallet.objects.create(apns_device=apns, wallet_hash=wallet_hash, last_active=timezone.now())

        assert _wallets(wallet_hash).count() == 2
