from django.core.management.base import BaseCommand

from main.models import WalletLookupKey
from main.utils.wallet_balances import clear_lookup_balance_cache


class Command(BaseCommand):
    help = (
        "Revoke (hard delete) wallet lookup keys by wallet hash. Use this when "
        "a wallet owner has lost access and can no longer revoke their own key."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'wallet_hashes',
            nargs='+',
            type=str,
            help='One or more wallet hashes whose lookup key should be revoked',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would be revoked without deleting anything',
        )

    def handle(self, *args, **options):
        wallet_hashes = options['wallet_hashes']
        dry_run = options['dry_run']

        revoked_count = 0

        for wallet_hash in wallet_hashes:
            # One key per wallet at most, so get() raises rather than
            # needing a filter+first.
            lookup_key = WalletLookupKey.objects.filter(
                wallet__wallet_hash=wallet_hash
            ).first()

            if not lookup_key:
                self.stdout.write(f'{wallet_hash}: no lookup key')
                continue

            self.stdout.write(
                f'{wallet_hash}: key id={lookup_key.id} '
                f'label={lookup_key.label or "-"} '
                f'created={lookup_key.date_created.isoformat()}'
            )

            if dry_run:
                self.stdout.write('  (dry run, not revoked)')
                continue

            lookup_key.delete()
            clear_lookup_balance_cache(wallet_hash)
            self.stdout.write(self.style.SUCCESS('  revoked'))
            revoked_count += 1

        prefix = 'would revoke' if dry_run else 'revoked'
        self.stdout.write(self.style.SUCCESS(f'{prefix} {revoked_count} key(s)'))
