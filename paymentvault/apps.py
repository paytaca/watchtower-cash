from django.apps import AppConfig


class PaymentVaultConfig(AppConfig):
    name = 'paymentvault'

    def ready(self):
        import paymentvault.signals