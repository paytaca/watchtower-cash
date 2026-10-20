from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.utils.translation import gettext_lazy as _
from push_notifications.models import GCMDevice, APNSDevice


# Create your models here.
class DeviceWallet(models.Model):
    gcm_device = models.ForeignKey(
        GCMDevice,
        related_name="device_wallets",
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )

    apns_device = models.ForeignKey(
        APNSDevice,
        related_name="device_wallets",
        on_delete=models.SET_NULL,
        null=True, blank=True
    )

    wallet_hash = models.CharField(max_length=70, db_index=True)

    # could add more settings later
    multi_wallet_index = models.IntegerField(null=True, blank=True)
    last_active = models.DateTimeField()


class OrderLiveActivityToken(models.Model):
    """
    Push destination for an order live activity.

    iOS activities get a dedicated, per-activity ActivityKit push token, so this
    is keyed by order (not wallet). Android has no such token and reuses the
    device FCM token, which is fine to store the same way.
    """

    class Platform(models.TextChoices):
        IOS = "ios", _("iOS")
        ANDROID = "android", _("Android")

    # No db_index here: `order_id` already leads the unique constraint below, so
    # that index serves order lookups and a second btree would be dead weight.
    order_id = models.BigIntegerField()
    token = models.CharField(max_length=512)
    platform = models.CharField(max_length=16, choices=Platform.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["order_id", "token", "platform"]]

    def __str__(self):
        return f"{self.order_id}:{self.platform}"
