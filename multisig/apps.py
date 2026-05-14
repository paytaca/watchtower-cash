from django.apps import AppConfig


class MultisigConfig(AppConfig):
    name = 'multisig'

    def ready(self):
        import multisig.signals

