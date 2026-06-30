import logging


logger = logging.getLogger(__name__)


def verify_wallet_ownership(user, wallet_hash):
    """Verify that the authenticated user owns the given wallet_hash.

    Checks the full chain:
      1. The user has a ``bitcoincash_address``.
      2. An ``Address`` record links that address to the wallet_hash.
      3. A ``NostrPubkey`` record exists for the wallet_hash.

    Returns ``(True, None)`` on success, ``(False, reason)`` on failure.
    """
    bitcoincash_address = getattr(user, 'bitcoincash_address', None)
    if not bitcoincash_address:
        logger.warning(
            f'Owner check failed for wallet {wallet_hash[:16]}... '
            f'— user has no bitcoincash_address'
        )
        return False, 'No address associated with user'

    from main.models import Address
    if not Address.objects.filter(
        address=bitcoincash_address,
        wallet__wallet_hash=wallet_hash,
    ).exists():
        logger.warning(
            f'Owner check failed for wallet {wallet_hash[:16]}... '
            f'— cash address is not linked to this wallet'
        )
        return False, 'Wallet does not belong to user'

    from nostr.models import NostrPubkey
    if not NostrPubkey.objects.filter(wallet_hash=wallet_hash).exists():
        logger.warning(
            f'Owner check failed for wallet {wallet_hash[:16]}... '
            f'— no NostrPubkey record'
        )
        return False, 'No nostr pubkey registered for this wallet'

    return True, None
