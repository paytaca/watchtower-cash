import logging
from django.apps import AppConfig


LOGGER = logging.getLogger("stablehedge")

class StablehedgeConfig(AppConfig):
    name = 'stablehedge'
