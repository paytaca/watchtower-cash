from django.db.models.signals import post_save
from django.dispatch import receiver

from paytacapos.models import Merchant

from purelypeer.vault import generate_merchant_vault


@receiver(post_save, sender=Merchant)
def post_create_merchant(sender, instance=None, created=False, **kwargs):
    if created or instance.vault is None:
        generate_merchant_vault(instance.id)
