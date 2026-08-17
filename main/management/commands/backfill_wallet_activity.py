from django.core.management.base import BaseCommand
from django.utils import timezone

from main.models import WalletActivity, WalletHistory


class Command(BaseCommand):
    help = 'One-time backfill of WalletActivity records from historical WalletHistory sends'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Only backfill sends on this UTC day (YYYY-MM-DD). Defaults to all history.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Count what would be created without writing anything',
        )
        parser.add_argument(
            '--progress-every',
            type=int,
            default=5000,
            help='Log progress every N records (default: 5000)',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        progress_every = options.get('progress_every', 5000)
        target_date = options.get('date')

        queryset = WalletHistory.objects.filter(
            record_type=WalletHistory.OUTGOING,
            wallet__isnull=False,
        ).select_related('wallet')

        if target_date:
            day = timezone.datetime.strptime(target_date, '%Y-%m-%d').date()
            queryset = queryset.filter(tx_timestamp__date=day)

        total = queryset.count()
        self.stdout.write(
            f"Backfilling WalletActivity from {total} outgoing WalletHistory records"
        )

        created = 0
        skipped = 0

        for idx, history in enumerate(queryset.iterator(chunk_size=2000)):
            activity_date = history.tx_timestamp.date() if history.tx_timestamp else timezone.now().date()

            if dry_run:
                was_created = not WalletActivity.objects.filter(
                    wallet=history.wallet,
                    history=history,
                    kind=WalletActivity.KIND_TRANSACTION_SEND,
                ).exists()
            else:
                _, was_created = WalletActivity.objects.get_or_create(
                    wallet=history.wallet,
                    history=history,
                    kind=WalletActivity.KIND_TRANSACTION_SEND,
                    defaults={
                        'activity_date': activity_date,
                        'amount': int(round(abs(history.amount) * 100_000_000)) if history.amount else None,
                    },
                )

            if was_created:
                created += 1
            else:
                skipped += 1

            if progress_every and (idx + 1) % progress_every == 0:
                self.stdout.write(
                    f"  [{idx + 1}/{total}] scanned, {created} created, {skipped} skipped"
                )

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created: {created}, Skipped (already exist): {skipped}"
        ))