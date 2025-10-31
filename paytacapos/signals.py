from django.db.models.signals import post_save
from django.dispatch import receiver

from paytacapos.models import Merchant
from paytacapos.utils.wallet_history import link_wallet_history

from main.models import WalletHistory
from main.utils.cache import clear_pos_wallet_history_cache

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
    pos_wallet_history = link_wallet_history(instance)

    if not pos_wallet_history:
        return pos_wallet_history

    wallet = instance.wallet
    if wallet:
        clear_pos_wallet_history_cache(wallet.wallet_hash, pos_wallet_history.posid)

    return pos_wallet_history
