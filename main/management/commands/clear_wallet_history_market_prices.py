from django.core.management.base import BaseCommand
from django.db import transaction
from main.models import WalletHistory


class Command(BaseCommand):
    help = "Clear market_prices for WalletHistory records matching a specific cashtoken category"

    def add_arguments(self, parser):
        parser.add_argument(
            'category',
            type=str,
            help='The cashtoken category to clear market_prices for'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without actually updating',
        )

    def handle(self, *args, **options):
        category = options['category']
        dry_run = options['dry_run']

        # Query WalletHistory records with the specified cashtoken category
        queryset = WalletHistory.objects.filter(
            cashtoken_ft__category=category
        ).select_related('cashtoken_ft')

        count = queryset.count()
        
        if count == 0:
            self.stdout.write(
                self.style.WARNING(
                    f'No WalletHistory records found for cashtoken category: {category}'
                )
            )
            return

        # Show records that will be updated
        records_with_prices = queryset.exclude(market_prices__isnull=True).exclude(market_prices={})
        records_with_prices_count = records_with_prices.count()

        self.stdout.write(
            f'Found {count} WalletHistory record(s) for category: {category}'
        )
        self.stdout.write(
            f'  - {records_with_prices_count} record(s) have market_prices set'
        )
        self.stdout.write(
            f'  - {count - records_with_prices_count} record(s) already have empty/null market_prices'
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING('\nDRY RUN - No changes will be made')
            )
            if records_with_prices_count > 0:
                self.stdout.write('\nRecords that would be updated:')
                for record in records_with_prices[:10]:  # Show first 10
                    self.stdout.write(
                        f'  - ID: {record.id}, TXID: {record.txid}, '
                        f'market_prices: {record.market_prices}'
                    )
                if records_with_prices_count > 10:
                    self.stdout.write(f'  ... and {records_with_prices_count - 10} more')
            return

        # Confirm before proceeding
        if records_with_prices_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    f'\nThis will clear market_prices for {records_with_prices_count} record(s).'
                )
            )
            confirm = input('Are you sure you want to continue? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING('Operation cancelled.'))
                return

        # Clear market_prices
        with transaction.atomic():
            updated = queryset.update(market_prices=None)
            
            # Also clear usd_price if it was set from market_prices
            # (This is optional - you may want to keep usd_price)
            # queryset.update(usd_price=None)

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully cleared market_prices for {updated} WalletHistory record(s)'
            )
        )







