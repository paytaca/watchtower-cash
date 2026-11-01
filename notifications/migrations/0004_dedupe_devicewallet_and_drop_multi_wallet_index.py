"""
Collapse duplicate DeviceWallet rows and drop `multi_wallet_index`.

`multi_wallet_index` was the app's vault position, not a stable identity: the
client reports whatever numeric slot the wallet currently occupies, and that
slot shifts on every vault reorder or deletion. Since the value was also used as
the grouping key when sending pushes, one wallet hash accumulated one
DeviceWallet row per index it had ever occupied, and every send fanned out once
per row — the same transaction produced one identical notification per row.

Dropping the column removes the grouping key. This migration first collapses the
rows it left behind so the natural key below can be applied.
"""

from django.db import migrations, models


def dedupe_device_wallets(apps, schema_editor):
    DeviceWallet = apps.get_model("notifications", "DeviceWallet")

    # Keep the most recently active row per (device, wallet_hash). Two separate
    # passes because a row can reference a GCM device, an APNS device, or
    # neither — grouping on both FK columns at once would treat NULLs as
    # distinct and leave duplicates behind.
    #
    # Duplicates are first unlinked (`<device>_id = NULL`) rather than deleted:
    # a row may carry both FKs, and deleting it outright would also drop the
    # other device's link to that wallet. A duplicate left with no device at all
    # cannot deliver a push, so it is deleted in the same pass.
    for device_field in ("gcm_device_id", "apns_device_id"):
        seen = set()
        duplicate_ids = []

        rows = (
            DeviceWallet.objects.filter(**{f"{device_field}__isnull": False})
            .order_by(device_field, "wallet_hash", "-last_active", "-id")
            .values_list("id", device_field, "wallet_hash")
        )
        for pk, device_id, wallet_hash in rows.iterator():
            key = (device_id, wallet_hash)
            if key in seen:
                duplicate_ids.append(pk)
            else:
                seen.add(key)

        if duplicate_ids:
            DeviceWallet.objects.filter(id__in=duplicate_ids).update(**{device_field: None})
            # A duplicate that only ever referenced this device has nothing
            # left to deliver to, so drop it instead of leaving a dead row.
            DeviceWallet.objects.filter(
                id__in=duplicate_ids,
                gcm_device__isnull=True,
                apns_device__isnull=True,
            ).delete()


def noop_reverse(apps, schema_editor):
    """De-duplication is not reversible; the dropped column is re-added empty."""


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0003_orderliveactivitytoken"),
    ]

    operations = [
        migrations.RunPython(dedupe_device_wallets, noop_reverse),
        migrations.RemoveField(
            model_name="devicewallet",
            name="multi_wallet_index",
        ),
        migrations.AddConstraint(
            model_name="devicewallet",
            constraint=models.UniqueConstraint(
                fields=["wallet_hash", "gcm_device"],
                name="unique_wallet_hash_per_gcm_device",
            ),
        ),
        migrations.AddConstraint(
            model_name="devicewallet",
            constraint=models.UniqueConstraint(
                fields=["wallet_hash", "apns_device"],
                name="unique_wallet_hash_per_apns_device",
            ),
        ),
    ]
