from django.apps import AppConfig

class MainConfig(AppConfig):
    name = 'main'
    
    def ready(self):
        from django.conf import settings
        import main.signals
        redis = settings.REDISKV
        redis.set('slpfountainheadsocket', 0)
        redis.set('slpbitcoinsocket', 0)
        redis_storage.set('slpstreamfountainheadsocket', 0)