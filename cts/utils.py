from django.conf import settings
from main.utils.queries.node import Node

settings.BCHN_HOST

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




