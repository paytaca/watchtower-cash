from django.apps import AppConfig

class MainConfig(AppConfig):
    name = 'main'
    
    def ready(self):
        import main.signals
        from django.conf import settings
        REDIS_STORAGE = settings.REDISKV
        REDIS_STORAGE.delete('ACTIVE-BLOCK')
        REDIS_STORAGE.delete('ACTIVE-BLOCK-TRANSACTIONS')
        REDIS_STORAGE.delete('ACTIVE-BLOCK-TRANSACTIONS-CURRENT-INDEX')
        REDIS_STORAGE.delete('ACTIVE-BLOCK-TRANSACTIONS-INDEX-LIMIT')
        REDIS_STORAGE.delete('ACTIVE-BLOCK-TRANSACTIONS-COUNT')
        REDIS_STORAGE.delete('GENESIS')
        REDIS_STORAGE.delete('READY')