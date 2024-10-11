from vouchers.models import MerchantVault, PosDeviceVault
from vouchers.vouchers import subscribe_vault_address
from main.models import Address

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=MerchantVault)
def post_create_merchant_vault(sender, instance=None, created=False, **kwargs):
    address = Address.objects.filter(address=instance.address)
    if not address.exists():
        subscribe_vault_address(instance.address)


@receiver(post_save, sender=PosDeviceVault)
def post_create_pos_device_vault(sender, instance=None, created=False, **kwargs):
    address = Address.objects.filter(address=instance.address)
    if not address.exists():
        subscribe_vault_address(instance.address)