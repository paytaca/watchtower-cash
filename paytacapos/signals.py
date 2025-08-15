from django.db.models.signals import post_save
from django.dispatch import receiver

from paytacapos.models import Merchant
from paytacapos.utils.wallet_history import link_wallet_history

from main.models import WalletHistory

from slugify import slugify


@receiver(post_save, sender=Merchant)
def post_create_merchant(sender, instance=None, created=False, **kwargs):
    if created:
        slug = slugify(instance.name)
        instance.slug = f'{slug}-{instance.id}'
        instance.save()

@receiver(post_save, sender=WalletHistory)
def post_create_wallet_history(sender, instance:WalletHistory, created:bool, **kwargs):
    if not created: return
    return link_wallet_history(instance)
