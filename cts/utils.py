from django.conf import settings

from main.models import (
    Address,
    BlockHeight,
    Transaction,
    Token,
    CashNonFungibleToken,
)
from main.tasks import process_input, process_output
from main.utils.cache import clear_wallet_balance_cache, clear_wallet_history_cache
from main.utils.queries.node import Node

NODE = Node()


def build_authchain(authhead, authbase, max_depth=1500):
    """
    Trace an authchain backwards from the authhead to the authbase via input 0.

    In the authguard covenant, the identity output is output 0 and is spent by input 0 of the
    next transaction (input 1 holds the authkey NFT). So each transaction's input 0 txid names
    its predecessor, letting us walk authhead -> ... -> authbase without any database or index.

    Returns the ordered list [authbase, ..., authhead].
    Node-only; performs no database reads or writes.
    """
    if authhead == authbase:
        return [authbase]

    chain = [authhead]
    seen = {authhead}
    current = authhead

    while True:
        # Read the predecessor from the raw vin: the parsed form skips inputs
        # without a resolvable address (and coinbase entries have no txid),
        # which would make inputs[0] the wrong input.
        raw = NODE.BCH._get_raw_transaction(current)
        if raw is None:
            raise ValueError(f"node has no tx {current}")

        vin = raw.get("vin") or []
        if not vin:
            raise ValueError(f"{current} has no inputs")

        prev = vin[0].get("txid")
        if not prev:
            raise ValueError(f"{current} input 0 has no prevout txid")

        if prev == authbase:
            break
        if prev in seen:
            raise ValueError("cycle detected; not an authchain")
        if len(chain) >= max_depth:
            raise ValueError("max depth reached; did not hit authbase")

        chain.append(prev)
        seen.add(prev)
        current = prev

    chain.append(authbase)
    chain.reverse()
    return chain


def get_authguard_address(authhead):
    """The authguard address = the authhead's index-0 output address."""
    head_tx = NODE.BCH.get_transaction(authhead)
    if head_tx is None:
        raise ValueError(f"node has no tx {authhead}")
    out0 = next((o for o in head_tx["outputs"] if o["index"] == 0), None)
    if not out0 or not out0.get("address"):
        raise ValueError(f"{authhead} has no index-0 output address")
    return out0["address"]


def resolve_block(tx):
    """Resolve a BlockHeight from a parsed tx's confirmations. Returns None if unknown."""
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
    # Look up only: creating a BlockHeight row triggers blockheight_post_save ->
    # block_setter(), which queues a full block reprocess (main/signals.py).
    return BlockHeight.objects.filter(number=number).first()


def assert_unspent_authhead(authhead):
    """
    Refuse to set a spent output as the authhead.

    Guards against a stale/fork head being posted: marking a spent txid `spent=False` would
    erase the DB link to the real head and make the endpoint serve false on-chain state.
    `gettxout` returns None when the output is spent (or spent in the mempool).
    """
    if NODE.BCH.get_tx_output(authhead, 0) is None:
        raise ValueError(f"{authhead}:0 is not an unspent output; refusing to set it as authhead")


def repair_authchain_minimal(chain):
    """
    Write the index-0 rows for a chain base -> head using direct ORM.

    Existing rows only get `spent`/`spending_txid` updated; missing rows are created minimally
    from the node's output 0. No BCMR, no post-save signals. Returns (updated, created).
    """
    assert_unspent_authhead(chain[-1])
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
            continue

        addr_obj, _ = Address.objects.get_or_create(address=o0["address"])
        # An authchain identity output always carries the token's NFT, so the row belongs to
        # the cashtoken. (A plain-BCH output 0 would need the 'bch' token instead, but that
        # does not occur on a real authchain.)
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
        ], ignore_conflicts=True)
        created += 1
    return updated, created


def repair_authchain_full(chain, authhead):
    """
    Write the index-0 rows through the normal ingestion path (process_output/process_input).

    This DOES fetch BCMR metadata and trigger the post-save side effects. Returns (updated, created).
    """
    assert_unspent_authhead(authhead)
    updated = 0
    created = 0
    for i, txid in enumerate(chain):
        head = (i == len(chain) - 1)
        link = "" if head else chain[i + 1]

        tx = NODE.BCH.get_transaction(txid)
        if tx is None:
            continue

        o0 = next((o for o in tx["outputs"] if o["index"] == 0), None)
        if not o0 or not o0.get("address"):
            continue

        block = resolve_block(tx)
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
            Transaction.objects.filter(txid=txid, index=0).update(spent=False, spending_txid="")

        if existed:
            updated += 1
        else:
            created += 1
    return updated, created


def clear_authguard_caches(authguard_address):
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
