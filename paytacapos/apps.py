from django.apps import AppConfig


class PaytacaposConfig(AppConfig):
    name = 'paytacapos'

    def ready(self):
        import paytacapos.signals