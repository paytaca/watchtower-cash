from django.apps import AppConfig

class MainConfig(AppConfig):
    name = 'main'
    
    def ready(self):
        import main.signals
        from main.tasks import REDIS_STORAGE, populate_token_addresses

        # Restart block scanning upon re-deployment
        REDIS_STORAGE.delete('PENDING-BLOCKS')
        REDIS_STORAGE.delete('ACTIVE-BLOCK')
        REDIS_STORAGE.delete('BITDBQUERY_COUNT')
        REDIS_STORAGE.delete('BITDBQUERY_COUNT')
        REDIS_STORAGE.set('READY', 1)

        populate_token_addresses.delay()
