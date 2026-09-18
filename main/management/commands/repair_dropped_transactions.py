from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from main.models import Transaction
from main.utils.queries.node import Node
from main.utils.transaction_processing import reverse_dropped_transaction

NODE = Node()


class Command(BaseCommand):
    help = (
        "One-time repair for transactions dropped from the mempool (e.g. the "
        "Cauldron conflicting-trades case). Reverses inputs marked spent and "
        "cleans up phantom unconfirmed outputs/history for txids that the node "
        "no longer knows about. Run with --dry-run first."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Only report txids that would be reversed; make no changes.',
        )
        parser.add_argument(
            '--min-age-minutes',
            type=int,
            default=10,
            help='Only consider unconfirmed txs older than this (default: 10).',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Number of txids to check per query (default: 500).',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Maximum number of txids to check in total (default: no limit).',
        )
        parser.add_argument(
            '--include-spent-txids',
            action='store_true',
            help=(
                'Also scan distinct spending_txids on spent inputs that have no '
                'confirmed transaction row. This is heavier but catches dropped '
                'txs whose outputs were all to untracked addresses.'
            ),
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        min_age_minutes = options['min_age_minutes']
        batch_size = options['batch_size']
        limit = options['limit']
        include_spent_txids = options['include_spent_txids']

        txids = []

        # 1. Unconfirmed transaction rows (covers tracked-output txs).
        qs = Transaction.objects.filter(blockheight__isnull=True)
        if min_age_minutes:
            cutoff = timezone.now() - timedelta(minutes=min_age_minutes)
            qs = qs.filter(date_created__lte=cutoff)
        txids += list(
            qs.values_list('txid', flat=True).distinct()[:batch_size]
        )
        self.stdout.write(
            f"Unconfirmed rows: found {len(txids)} candidate txid(s)"
        )

        # 2. Optionally, spending_txids on spent inputs without a confirmed row.
        if include_spent_txids:
            confirmed_txids = Transaction.objects.filter(
                blockheight__isnull=False
            ).values_list('txid', flat=True)
            spent_txids = (
                Transaction.objects.filter(spent=True)
                .exclude(spending_txid='')
                .exclude(spending_txid__isnull=True)
                .exclude(spending_txid__in=confirmed_txids)
                .values_list('spending_txid', flat=True)
                .distinct()[:batch_size]
            )
            spent_txids = list(spent_txids)
            self.stdout.write(
                f"Spent-input spending_txids: found {len(spent_txids)} candidate(s)"
            )
            txids += spent_txids

        # dedupe while preserving order
        txids = list(dict.fromkeys(txids))
        if limit:
            txids = txids[:limit]

        if not txids:
            self.stdout.write(self.style.SUCCESS("No candidate txids found."))
            return

        self.stdout.write(f"Checking {len(txids)} txid(s) against the node...")

        dropped = []
        for txid in txids:
            try:
                tx = NODE.BCH.get_transaction(txid)
            except Exception as exc:
                self.stderr.write(f"  ! node query failed for {txid}: {exc}")
                continue

            if tx:
                continue
            dropped.append(txid)

        if not dropped:
            self.stdout.write(
                self.style.SUCCESS("No dropped transactions found; nothing to repair.")
            )
            return

        self.stdout.write(
            f"Found {len(dropped)} dropped transaction(s): {dropped}"
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("Dry run: no changes were made.")
            )
            return

        for txid in dropped:
            try:
                summary = reverse_dropped_transaction(txid)
                self.stdout.write(
                    self.style.SUCCESS(f"Reversed {txid}: {summary}")
                )
            except Exception as exc:
                self.stderr.write(f"  ! failed to reverse {txid}: {exc}")

        self.stdout.write(self.style.SUCCESS("Repair complete."))