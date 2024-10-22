from django.apps import AppConfig


class PaytacaposConfig(AppConfig):
    name = 'paytacapos'

    def ready(self):
        import paytacapos.signals
        from paytacapos.models import Merchant

        # upate default merchant index value of existing merchants
        verified_merchants = Merchant.objects.filter(
            active=True,
            verified=True
        )
        verified_merchants.update(index=None)
