from django.db.models.signals import post_migrate
from django.apps import AppConfig


def generate_vault_for_existing_merchants(*args, **kwargs):
    from vouchers.vault import generate_merchant_vault
    from paytacapos.models import Merchant

    for merchant in Merchant.objects.filter(vault__isnull=True):
        generate_merchant_vault(merchant.id)


class PaytacaposConfig(AppConfig):
    # default_auto_field = 'django.db.models.BigAutoField'
    name = 'paytacapos'

    def ready(self):
        import paytacapos.signals

        post_migrate.connect(generate_vault_for_existing_merchants, sender=self)
