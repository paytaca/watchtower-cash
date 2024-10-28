from django.conf import settings
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

from anyhedge.utils.address import pubkey_to_cashaddr
from main.utils.subscription import new_subscription
from main.models import Project, Wallet
from .models import PaymentVault


@receiver(post_save, sender=PaymentVault)
def payment_vault_post_save(sender, instance=None, created=False, **kwargs):
    paytaca_prod = Project.objects.get(name__iexact='paytaca')
    paytaca_test = Project.objects.get(name__iexact='paytaca test')

    project_id = {
        'mainnet': paytaca_prod.id,
        'chipnet': paytaca_test.id
    }
    project_id = project_id[settings.BCH_NETWORK]
    vault_subscription_data = {
        'address': instance.address,
        'project_id': project_id,
    }
    merchant_subscription_data = vault_subscription_data
    merchant_subscription_data['address'] = pubkey_to_cashaddr(instance.merchant.pubkey)
    merchant_subscription_data['wallet_hash'] = instance.merchant.wallet_hash

    # added try catch here for already subscribed addresses error
    try:
        new_subscription(**vault_subscription_data)
        new_subscription(**merchant_subscription_data)
    except:
        pass