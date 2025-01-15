from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Clear balance and transaction history caches"

    def handle(self, *args, **options):

        # delete balance caches
        cache = settings.REDISKV
        balance_keys = cache.keys(f'wallet:balance:*')
        if balance_keys:
            cache.delete(*balance_keys)

        # delete wallet history caches
        history_cache_keys = cache.keys(f'wallet:history:*')
        if history_cache_keys:
            cache.delete(*history_cache_keys)
