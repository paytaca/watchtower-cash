from django.db import models, transaction
from django.utils import timezone
from push_notifications.models import GCMDevice, APNSDevice
from ..models import DeviceWallet


@transaction.atomic
def remove_inactive_device_wallets():
    no_device = models.Q(gcm_device__isnull=True, apns_device__isnull=True)
    inactive_for_a_month = models.Q(
        last_active__lt=timezone.now() - timezone.timedelta(days=30)
    )

    DeviceWallet.objects.filter(no_device | inactive_for_a_month).delete()
    GCMDevice.objects.annotate(device_wallets_count=models.Count("device_wallets")).filter(device_wallets_count=0).delete()
    APNSDevice.objects.annotate(device_wallets_count=models.Count("device_wallets")).filter(device_wallets_count=0).delete()


@transaction.atomic
def remove_inactive_devices():
    GCMDevice.objects.filter(active=False).delete()
    APNSDevice.objects.filter(active=False).delete()
    DeviceWallet.objects.filter(gcm_device__isnull=True, apns_device__isnull=True).delete()
