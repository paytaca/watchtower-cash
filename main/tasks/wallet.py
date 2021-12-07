from celery import shared_task
from main.models import (
    Address,
    WalletHistory,
    Transaction,
    WalletNftToken
)


@shared_task(bind=True, queue='celery_rebuild_history')
def rebuild_wallet_history(wallet_id):
    addresses = Address.objects.filter(wallet_id=wallet_id)
    for address in addresses:
        for transaction in address.transactions.all():
            history_check = WalletHistory.objects.filter(
                txid=transaction.txid,
                recipients__contains=[address.address]
            )
            if not history_check.exists():
                transaction.save()

            if transaction.token.token_type == 65:
                wallet_nft_token_check = WalletNftToken.objects.filter(
                    wallet_id=wallet_id,
                    token=transaction.token
                )
                if wallet_nft_token_check.exists():
                    wallet_nft_token = wallet_nft_token_check.last()
                    if  wallet_nft_token.date_dispensed is None and transaction.spent:
                        try:
                            spending_tx = Transaction.objects.get(txid=transaction.spending_txid)
                            wallet_nft_token.date_dispensed = spending_tx.date_created
                        except Transaction.DoesNotExist:
                            pass
                else:
                    wallet_nft_token = WalletNftToken(
                        wallet_id=wallet_id,
                        token=transaction.token,
                        date_acquired=transaction.date_created,
                        acquisition_transaction=transaction
                    )
                    wallet_nft_token.save()
