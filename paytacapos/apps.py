from django.apps import AppConfig
from django.db.models.signals import post_migrate


def set_index_of_existing_merchants(*args, **kwargs):
    from paytacapos.models import Merchant

    # upate default merchant index value of existing merchants
    verified_merchants = Merchant.objects.filter(
        active=True,
        verified=True
    )
    verified_merchants.update(index=None)


class PaytacaposConfig(AppConfig):
    name = 'paytacapos'

    def ready(self):
        import paytacapos.signals

        post_migrate.connect(set_index_of_existing_merchants, sender=self)
