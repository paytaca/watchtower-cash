from django.apps import AppConfig

class MainConfig(AppConfig):
    name = 'main'
    
    def ready(self):
        # from django.conf import settings
        import main.signals
        # redis = settings.REDISKV
        # redis.set('SLP-BITCOIN-SOCKET-STATUS', 0)
        # redis.set('BITSOCKET', 0)