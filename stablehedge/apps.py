import logging
from django.apps import AppConfig


LOGGER = logging.getLogger("stablehedge")

class StablehedgeConfig(AppConfig):
    name = 'stablehedge'
    
    def ready(self):
        try:
            from stablehedge.functions.auth_key import subscribe_auth_key
            subscribe_auth_key()
        except Exception as e:
            LOGGER.exception(e)
