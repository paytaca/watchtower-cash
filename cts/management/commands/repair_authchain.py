from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from main.models import (
    Address,
    BlockHeight,
    Subscription,
    Transaction,
    Token,
    CashNonFungibleToken,
)
from main.tasks import process_input, process_output
from main.utils.subscription import new_subscription
from main.utils.cache import clear_wallet_balance_cache, clear_wallet_history_cache

from cts.utils import NODE, build_authchain


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
        apply = options["apply"]
        full = options["full"]

        self.stdout.write("repair_authchain options:")
        self.stdout.write(f"  --authhead  = {authhead}")
        self.stdout.write(f"  --authbase  = {authbase}")
        self.stdout.write(f"  --max-depth = {options['max_depth']}")
        self.stdout.write(f"  --apply     = {apply}")
        self.stdout.write(f"  --full      = {full}")

        # 1. Trace the chain from the node (no DB).
        try:
            chain = build_authchain(authhead, authbase, max_depth=options["max_depth"])
        except ValueError as exc:
            raise CommandError(str(exc))

        # 2. Resolve the authguard address = the authhead's index-0 output address.
        head_tx = NODE.BCH.get_transaction(authhead)
        if head_tx is None:
            raise CommandError(f"node has no tx {authhead}")
        out0 = next((o for o in head_tx["outputs"] if o["index"] == 0), None)
        if not out0 or not out0.get("address"):
            raise CommandError(f"{authhead} has no index-0 output address")
        authguard_address = out0["address"]

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
        elif apply:
            response = new_subscription(address=authguard_address)
            self.stdout.write(f"Subscribed {authguard_address}: {response}")
        else:
            self.stdout.write(f"Address {authguard_address} is NOT subscribed (dry-run: would subscribe).")

        # 4. Repair index-0 rows base -> head.
        if not apply:
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

        if full:
            self.stdout.write("Mode: --full (process_output/process_input; BCMR + side effects).")
            updated, created = self._repair_full(chain, authhead)
        else:
            self.stdout.write("Mode: minimal (direct ORM; no BCMR, no signals).")
            updated, created = self._repair_minimal(chain)

        self._clear_caches(authguard_address)

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

    def _repair_minimal(self, chain):
        """Direct ORM writes for index-0 rows. No BCMR, no post-save signals."""
        updated = 0
        created = 0
        for i, txid in enumerate(chain):
            head = (i == len(chain) - 1)
            link = "" if head else chain[i + 1]

            rows = Transaction.objects.filter(txid=txid, index=0)
            if rows.exists():
                rows.update(spent=not head, spending_txid=link)
                updated += 1
                continue

            tx = NODE.BCH.get_transaction(txid)
            o0 = next((o for o in tx["outputs"] if o["index"] == 0), None) if tx else None
            if not o0 or not o0.get("address"):
                self.stderr.write(f"skip {txid}: no index-0 output")
                continue

            addr_obj, _ = Address.objects.get_or_create(address=o0["address"])
            token_obj, token_created = Token.objects.get_or_create(
                tokenid=settings.WT_DEFAULT_CASHTOKEN_ID
            )
            if token_created:
                token_obj.name = "CashToken - "
                token_obj.token_ticker = "CT-" + token_obj.tokenid[0:6]
                token_obj.save()

            token_data = o0.get("token_data") or {}
            nft = None
            if token_data.get("category"):
                nft_data = token_data.get("nft") or {}
                nft, _ = CashNonFungibleToken.objects.get_or_create(
                    current_txid=txid,
                    current_index=0,
                    defaults={
                        "category": token_data["category"],
                        "capability": nft_data.get("capability", ""),
                        "commitment": nft_data.get("commitment", ""),
                    },
                )

            amount = None
            if token_data.get("amount") is not None:
                try:
                    amount = int(token_data["amount"])
                except (TypeError, ValueError):
                    amount = None

            Transaction.objects.bulk_create([
                Transaction(
                    txid=txid,
                    address=addr_obj,
                    token=token_obj,
                    cashtoken_nft=nft,
                    index=0,
                    value=o0.get("value", 0),
                    amount=amount,
                    source="authchain_repair",
                    spent=not head,
                    spending_txid=link,
                )
            ])
            created += 1
        return updated, created

    def _repair_full(self, chain, authhead):
        """Full ingestion path via process_output/process_input (BCMR + post-save side effects)."""
        updated = 0
        created = 0
        for i, txid in enumerate(chain):
            head = (i == len(chain) - 1)
            link = "" if head else chain[i + 1]

            tx = NODE.BCH.get_transaction(txid)
            if tx is None:
                self.stderr.write(f"skip {txid}: node has no tx")
                continue

            o0 = next((o for o in tx["outputs"] if o["index"] == 0), None)
            if not o0 or not o0.get("address"):
                self.stderr.write(f"skip {txid}: no index-0 output")
                continue

            block = self._resolve_block(tx)
            block_id = block.id if block else None
            existed = Transaction.objects.filter(txid=txid, index=0).exists()

            process_output(
                o0,
                txid,
                block_id=block_id,
                force_create=True,
                spending_txid=link,
                send_client_acknowledgement=False,
            )

            # Link the tx's other inputs (authkey, funding, ...) to their source outputs.
            for tx_input in tx["inputs"]:
                process_input(
                    tx_input,
                    txid,
                    block_id=block_id,
                    force_create=True,
                    send_client_acknowledgement=False,
                )

            # process_output/save_record won't flip an already-spent row back to unspent.
            if head:
                Transaction.objects.filter(txid=txid, index=0).update(
                    spent=False, spending_txid=""
                )

            if existed:
                updated += 1
            else:
                created += 1
        return updated, created

    def _resolve_block(self, tx):
        confirmations = tx.get("confirmations")
        if not confirmations:
            return None
        try:
            latest = NODE.BCH.get_latest_block()
        except Exception:
            return None
        number = int(latest) - int(confirmations) + 1
        if number < 0:
            return None
        block, _ = BlockHeight.objects.get_or_create(number=number)
        return block

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

    @staticmethod
    def _clear_caches(authguard_address):
        cache = settings.REDISKV
        addresses = {authguard_address}
        addr_obj = Address.objects.filter(address=authguard_address).select_related("wallet").first()
        if addr_obj and addr_obj.token_address:
            addresses.add(addr_obj.token_address)

        for address in addresses:
            cache.delete(f"address:balance:bch:{address}:False")
            cache.delete(f"address:balance:bch:{address}:True")

        if addr_obj and addr_obj.wallet:
            wallet_hash = addr_obj.wallet.wallet_hash
            clear_wallet_balance_cache(wallet_hash)
            clear_wallet_history_cache(wallet_hash)
