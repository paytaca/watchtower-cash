import logging
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from main.utils.cache import clear_wallet_history_cache_for_txid

logger = logging.getLogger(__name__)


@receiver(post_save, sender='memos.Memo', dispatch_uid='memos.signals.memo_post_save')
def memo_post_save(sender, instance=None, created=False, **kwargs):
    """
    Clear wallet history cache for the transaction when a memo is created or updated.
    Only clears the specific pages that contain the affected transaction.
    """
    if not instance or not instance.wallet_hash or not instance.txid:
        return
    
    try:
        clear_wallet_history_cache_for_txid(instance.wallet_hash, instance.txid)
        logger.debug(
            f"Cleared wallet history cache for memo (wallet_hash={instance.wallet_hash}, "
            f"txid={instance.txid}, created={created})"
        )
    except Exception as e:
        logger.error(
            f"Error clearing wallet history cache for memo: {e}",
            exc_info=True
        )


@receiver(pre_delete, sender='memos.Memo', dispatch_uid='memos.signals.memo_pre_delete')
def memo_pre_delete(sender, instance=None, **kwargs):
    """
    Clear wallet history cache for the transaction when a memo is deleted.
    Only clears the specific pages that contain the affected transaction.
    """
    if not instance or not instance.wallet_hash or not instance.txid:
        return
    
    try:
        clear_wallet_history_cache_for_txid(instance.wallet_hash, instance.txid)
        logger.debug(
            f"Cleared wallet history cache for deleted memo (wallet_hash={instance.wallet_hash}, "
            f"txid={instance.txid})"
        )
    except Exception as e:
        logger.error(
            f"Error clearing wallet history cache for deleted memo: {e}",
            exc_info=True
        )




