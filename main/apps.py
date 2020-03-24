from django.apps import AppConfig

class MainConfig(AppConfig):
    name = 'main'

    def ready(self):
        from django.conf import settings
        redis = settings.REDISKV
        redis.set('slpfountainheadsocket', 0)
        redis.set('slpbitcoinsocket', 0) 