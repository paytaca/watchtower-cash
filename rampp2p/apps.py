from django.apps import AppConfig


class Rampp2PConfig(AppConfig):
    name = 'rampp2p'

    def ready(self):
        import rampp2p.signals
