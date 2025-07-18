from django.core.management.base import BaseCommand

from stablehedge.functions.auth_key import subscribe_auth_key


class Command(BaseCommand):
    help = "Subscribes the wallet that holds the auth keys for Stablehedge."

    def handle(self, *args, **options):
        subscribe_auth_key()
