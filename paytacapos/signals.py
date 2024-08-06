from django.db.models.signals import post_save
from django.dispatch import receiver

from paytacapos.models import Merchant, PosDevice
from vouchers.vault import generate_voucher_vault

from slugify import slugify


@receiver(post_save, sender=Merchant)
def post_create_merchant(sender, instance=None, created=False, **kwargs):
    if created:
        slug = slugify(instance.name)
        instance.slug = f'{slug}-{instance.id}'
        instance.save()


@receiver(post_save, sender=PosDevice)
def post_create_pos_device(sender, instance=None, created=False, **kwargs):
    if created:
        generate_voucher_vault(instance.id)