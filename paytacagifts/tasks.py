from celery import shared_task
from paytacagifts.models import Gift, Claim
from main.models import Transaction


@shared_task(queue='monitor-gifts')
def check_unfunded_gifts():
    unfunded_gifts = Gift.objects.filter(date_funded__isnull=True)
    for gift in unfunded_gifts:
        funding_check = Transaction.objects.filter(address__address=gift.address)
        if funding_check.exists():
            funding_tx = funding_check.first()
            gift.date_funded = funding_tx.date_created
            gift.save()


@shared_task(queue='monitor-gifts')
def check_unclaimed_gifts():
    funded_gifts = Gift.objects.filter(date_funded__isnull=False)
    for gift in funded_gifts:
        funding_tx = Transaction.objects.filter(
            address__address=gift.address
        ).first()
        if funding_tx:
            if funding_tx.spent:
                # Determine which claim succeeded
                txs = Transaction.objects.filter(txid=funding_tx.spending_txid)
                for tx in txs:
                    if tx.wallet:
                        claim_check = Claim.objects.filter(gift=gift, wallet__wallet_hash=tx.wallet.wallet_hash)
                        if claim_check.exists():
                            # Udpate gift fields
                            gift.date_claimed = tx.tx_timestamp
                            gift.claim_txid = funding_tx.spending_txid
                            gift.save()

                            # Mark claim as succeeded
                            claim = claim_check.latest('date_created')
                            claim.succeeded = True
                            claim.save()
