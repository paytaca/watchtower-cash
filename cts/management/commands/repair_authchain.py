from django.core.management.base import BaseCommand, CommandError

from main.models import Subscription, Transaction
from main.utils.subscription import new_subscription

from cts.utils import (
    build_authchain,
    clear_authguard_caches,
    get_authguard_address,
    repair_authchain_full,
    repair_authchain_minimal,
)


class Command(BaseCommand):
    help = (
        "Repair the authchain in the DB from the node. Traces [authbase, ..., authhead], "
        "ensures the authhead's address is subscribed, and rebuilds the index-0 (identity "
        "output) rows + spending_txid links. Node-only trace; no BCMR, no wallet history."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--authhead",
            type=str,
            required=True,
            help="The authhead txid (current unspent identity output).",
        )
        parser.add_argument(
            "--authbase",
            type=str,
            required=True,
            help="The authbase txid (the authchain's index-0 base).",
        )
        parser.add_argument(
            "--max-depth",
            type=int,
            default=1500,
            help="Maximum number of links to walk before giving up (default: 1500).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually write changes. Without this it is a dry-run.",
        )
        parser.add_argument(
            "--full",
            action="store_true",
            help=(
                "Use process_output/process_input so rows are written exactly like normal "
                "ingestion (BCMR metadata, cashtoken_ft/nft, wallet, blockheight). This DOES "
                "fetch BCMR metadata and trigger the post-save side effects. Default is the "
                "minimal, side-effect-free write."
            ),
        )

    def handle(self, *args, **options):
        authhead = options["authhead"]
        authbase = options["authbase"]
        do_apply = options["apply"]
        full = options["full"]

        self.stdout.write("repair_authchain options:")
        self.stdout.write(f"  --authhead  = {authhead}")
        self.stdout.write(f"  --authbase  = {authbase}")
        self.stdout.write(f"  --max-depth = {options['max_depth']}")
        self.stdout.write(f"  --apply     = {do_apply}")
        self.stdout.write(f"  --full      = {full}")

        # 1. Trace the chain from the node (no DB).
        try:
            chain = build_authchain(authhead, authbase, max_depth=options["max_depth"])
        except ValueError as exc:
            raise CommandError(str(exc))

        # 2. Resolve the authguard address = the authhead's index-0 output address.
        try:
            authguard_address = get_authguard_address(authhead)
        except ValueError as exc:
            raise CommandError(str(exc))

        self.stdout.write(f"Authchain ({len(chain)} links), authguard address {authguard_address}:")
        for txid in chain:
            marker = " <- authhead" if txid == authhead else (" <- authbase" if txid == authbase else "")
            self.stdout.write(f"  {txid}{marker}")

        # 3. Ensure the authhead's address is subscribed.
        subscribed = Subscription.objects.filter(
            address__address=authguard_address
        ).exists() or Subscription.objects.filter(
            address__token_address=authguard_address
        ).exists()

        if subscribed:
            self.stdout.write(f"Address {authguard_address} is already subscribed.")
        elif do_apply:
            response = new_subscription(address=authguard_address)
            self.stdout.write(f"Subscribed {authguard_address}: {response}")
        else:
            self.stdout.write(f"Address {authguard_address} is NOT subscribed (dry-run: would subscribe).")

        # 4. Repair index-0 rows base -> head.
        if not do_apply:
            resolved_ok, resolved_txid = self._diagnose(chain, authhead, authbase)
            if resolved_ok:
                self.stdout.write(self.style.SUCCESS(
                    f"Authchain already resolved to authhead {authhead}. No repair needed."
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f"Authchain is BROKEN/unresolved (DB walk resolved {resolved_txid}, "
                    f"expected {authhead}). Run with --apply to repair."
                ))
            self.stdout.write(self.style.WARNING("Dry-run: no rows written."))
            return

        try:
            if full:
                self.stdout.write("Mode: --full (process_output/process_input; BCMR + side effects).")
                updated, created = repair_authchain_full(chain, authhead)
            else:
                self.stdout.write("Mode: minimal (direct ORM; no BCMR, no signals).")
                updated, created = repair_authchain_minimal(chain)
        except ValueError as exc:
            raise CommandError(str(exc))

        clear_authguard_caches(authguard_address)

        self.stdout.write(self.style.SUCCESS(
            f"Repaired authchain: {updated} row(s) updated, {created} row(s) created."
        ))

        # 5. Verify with the same walk the endpoint uses.
        resolved_ok, resolved_txid = self._diagnose(chain, authhead, authbase)
        if resolved_ok:
            self.stdout.write(self.style.SUCCESS(f"Verified: DB walk resolves authhead {authhead}."))
        else:
            self.stderr.write(self.style.ERROR(
                f"Verification failed: DB walk resolved {resolved_txid}, expected {authhead}."
            ))

    def _diagnose(self, chain, authhead, authbase):
        """
        Print the current DB state of every index-0 link and whether the chain resolves.
        Read-only. Returns (resolved_ok, resolved_txid).
        """
        self.stdout.write("Diagnosing current DB state (index-0 rows):")
        for i, txid in enumerate(chain):
            head = (i == len(chain) - 1)
            expected_spent = not head
            expected_link = "" if head else chain[i + 1]

            row = Transaction.objects.filter(txid=txid, index=0).first()

            if row is None:
                status = "MISSING"
            elif row.spent != expected_spent:
                status = "SPENT-MISMATCH"
            elif row.spent and row.spending_txid != expected_link:
                status = "LINK-MISMATCH" if row.spending_txid else "DANGLING"
            else:
                status = "OK"

            marker = " <- authhead" if head else (" <- authbase" if txid == authbase else "")
            if row is None:
                detail = ""
            else:
                link_display = row.spending_txid if row.spending_txid else "''"
                detail = f"  spent={row.spent} spending_txid={link_display}"
            self.stdout.write(f"  {txid}  {status}{detail}{marker}")

        resolved = self._db_walk(authbase)
        resolved_txid = resolved.txid if resolved else None
        return (resolved_txid == authhead), resolved_txid

    @staticmethod
    def _db_walk(authbase):
        """Replicate Authhead.get_authhead: follow index-0 spending_txid to the unspent head."""
        current = authbase
        seen = set()
        while current and current not in seen:
            seen.add(current)
            row = Transaction.objects.filter(txid=current, index=0).first()
            if row is None:
                return None
            if not row.spent:
                return row
            current = row.spending_txid
        return None
