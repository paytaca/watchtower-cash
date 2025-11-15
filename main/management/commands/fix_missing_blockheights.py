from django.core.management.base import BaseCommand
from django.db.models import Max
from main.models import Transaction, BlockHeight
from main.tasks import NODE
import logging

LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fix missing blockheight values in Transaction records by querying the BCH node"

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=1000,
            help='Number of transactions to process (default: 1000)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        dry_run = options['dry_run']

        # Query transactions without blockheight, ordered by date_created descending
        # Get unique txids with their latest date_created to ensure we process latest first
        unique_txids_with_dates = Transaction.objects.filter(
            blockheight__isnull=True
        ).values('txid').annotate(
            latest_date=Max('date_created')
        ).order_by('-latest_date')[:limit]
        
        unique_txids_list = [item['txid'] for item in unique_txids_with_dates]
        unique_count = len(unique_txids_list)
        
        if unique_count == 0:
            self.stdout.write(self.style.SUCCESS('No transactions found without blockheight'))
            return

        # Get total count of transaction records (for statistics)
        total_count = Transaction.objects.filter(
            blockheight__isnull=True,
            txid__in=unique_txids_list
        ).count()

        self.stdout.write(f'Found {total_count} transaction records without blockheight')
        self.stdout.write(f'Processing {unique_count} unique transaction IDs...')
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        stats = {
            'processed': 0,
            'updated': 0,
            'skipped_mempool': 0,
            'errors': 0
        }

        # Process each unique txid
        for idx, txid in enumerate(unique_txids_list, 1):
            try:
                self.stdout.write(f'Processing {idx}/{unique_count}: {txid}...', ending='')
                
                # Get raw transaction with verbosity=2 to get blockhash if confirmed
                raw_tx = NODE.BCH._get_raw_transaction(txid, verbosity=2)
                
                if not raw_tx:
                    self.stdout.write(self.style.ERROR(' Not found in node'))
                    stats['errors'] += 1
                    continue

                # Check if transaction is confirmed (has blockhash)
                if 'blockhash' not in raw_tx:
                    self.stdout.write(self.style.WARNING(' Still in mempool (skipped)'))
                    stats['skipped_mempool'] += 1
                    continue

                # Get block info to extract height
                blockhash = raw_tx['blockhash']
                connection = NODE.BCH._get_rpc_connection()
                try:
                    block_info = connection.getblock(blockhash)
                    block_height = block_info['height']
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f' Error getting block info: {str(e)}'))
                    stats['errors'] += 1
                    continue
                finally:
                    NODE.BCH._close_connection(connection)

                # Get or create BlockHeight object
                blockheight_obj, created = BlockHeight.objects.get_or_create(number=block_height)
                
                if created:
                    self.stdout.write(f' Created BlockHeight {block_height}')
                else:
                    self.stdout.write(f' Using existing BlockHeight {block_height}')

                # Update all transactions with this txid
                tx_count = Transaction.objects.filter(txid=txid).count()
                
                if not dry_run:
                    updated_count = Transaction.objects.filter(txid=txid).update(
                        blockheight_id=blockheight_obj.id
                    )
                    self.stdout.write(
                        self.style.SUCCESS(f' Updated {updated_count} transaction(s)')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f' Would update {tx_count} transaction(s)')
                    )

                stats['processed'] += 1
                stats['updated'] += tx_count

            except Exception as e:
                self.stdout.write(self.style.ERROR(f' Error: {str(e)}'))
                LOGGER.exception(f'Error processing transaction {txid}')
                stats['errors'] += 1

        # Display statistics
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Statistics:'))
        self.stdout.write(f'  Total unique txids processed: {stats["processed"]}')
        self.stdout.write(f'  Transactions updated: {stats["updated"]}')
        self.stdout.write(f'  Skipped (mempool): {stats["skipped_mempool"]}')
        self.stdout.write(f'  Errors: {stats["errors"]}')
        self.stdout.write(self.style.SUCCESS('=' * 60))

