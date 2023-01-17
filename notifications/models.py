from django.db import models
from django.contrib.postgres.fields import ArrayField
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
    last_active = models.DateTimeField()