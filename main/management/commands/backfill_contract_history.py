import logging
from django.core.management.base import BaseCommand

from main.models import Transaction, ContractHistory
from main.tasks import parse_contract_history
from main.utils.address_validator import is_p2sh_address

LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Backfill missing outgoing ContractHistory records for P2SH (contract) addresses'

    def add_arguments(self, parser):
        parser.add_argument(
            '--address',
            type=str,
            help='Only process this specific P2SH address (e.g. bitcoincash:p...)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-process even if an outgoing record already exists',
        )
        parser.add_argument(
            '--progress-every',
            type=int,
            default=1000,
            help='Log progress every N records (default: 1000)',
        )

    def handle(self, *args, **options):
        target_address = options.get('address')
        force = options.get('force', False)
        progress_every = options.get('progress_every', 1000)

        if target_address and not is_p2sh_address(target_address):
            self.stderr.write(
                self.style.ERROR(f"Address {target_address} is not a P2SH address")
            )
            return

        # Find all P2SH addresses that have spent (outgoing) transactions
        # by looking at Transaction records with spending_txid set
        filters = {
            'spending_txid__isnull': False,
        }
        if target_address:
            filters['address__address'] = target_address

        p2sh_spent_txns = (
            Transaction.objects
            .filter(**filters)
            .exclude(spending_txid='')
            .select_related('address')
            .order_by('address__address', 'spending_txid')
        )

        total = p2sh_spent_txns.count()
        self.stdout.write(f"Scanning {total} spent transaction records...")

        processed = set()  # (address, spending_txid) dedup
        triggered = 0
        skipped = 0

        for idx, txn in enumerate(p2sh_spent_txns.iterator(chunk_size=2000)):
            if not is_p2sh_address(txn.address.address):
                continue

            key = (txn.address.address, txn.spending_txid)
            if key in processed:
                continue
            processed.add(key)

            addr, spending_txid = key

            if not force:
                # Check if a ContractHistory record for this outgoing tx already exists
                exists = ContractHistory.objects.filter(
                    address=txn.address,
                    txid=spending_txid,
                    record_type='outgoing',
                ).exists()

                if exists:
                    skipped += 1
                    if progress_every and (idx + 1) % progress_every == 0:
                        self.stdout.write(
                            f"  [{idx + 1}/{total}] scanned, "
                            f"{triggered} triggered, {skipped} skipped (existing)"
                        )
                    continue

            LOGGER.info(f"Triggering contract history for {addr} | outgoing txid={spending_txid}")
            parse_contract_history.delay(spending_txid, addr)
            triggered += 1

            if progress_every and (idx + 1) % progress_every == 0:
                self.stdout.write(
                    f"  [{idx + 1}/{total}] scanned, "
                    f"{triggered} triggered, {skipped} skipped"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Triggered: {triggered}, Skipped (already exist): {skipped}"
            )
        )
