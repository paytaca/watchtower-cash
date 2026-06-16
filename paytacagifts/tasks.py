from celery import shared_task
from paytacagifts.models import Gift, Claim
from main.models import Transaction


@shared_task(queue='monitor-gifts')
def check_unfunded_gifts():
    unfunded_gifts = list(Gift.objects.filter(date_funded__isnull=True))
    if not unfunded_gifts:
        return

    addresses = [g.address for g in unfunded_gifts if g.address]
    if not addresses:
        return

    funding_txs = Transaction.objects.filter(
        address__address__in=addresses
    ).values('address__address', 'date_created')

    tx_map = {tx['address__address']: tx['date_created'] for tx in funding_txs}

    for gift in unfunded_gifts:
        if gift.address in tx_map:
            gift.date_funded = tx_map[gift.address]

    updated = [g for g in unfunded_gifts if g.date_funded is not None]
    if updated:
        Gift.objects.bulk_update(updated, ['date_funded'])


@shared_task(queue='monitor-gifts')
def check_unclaimed_gifts():
    funded_gifts = list(Gift.objects.filter(
        date_funded__isnull=False,
        date_claimed__isnull=True
    ))
    if not funded_gifts:
        return

    addresses = [g.address for g in funded_gifts if g.address]
    if not addresses:
        return

    funding_txs = Transaction.objects.filter(
        address__address__in=addresses,
        spent=True
    ).values('address__address', 'spending_txid')

    funding_by_address = {tx['address__address']: tx for tx in funding_txs}
    if not funding_by_address:
        return

    spending_txids = [tx['spending_txid'] for tx in funding_txs if tx['spending_txid']]
    if not spending_txids:
        return

    spending_txs = Transaction.objects.filter(
        txid__in=spending_txids
    ).select_related('wallet').values('txid', 'wallet__wallet_hash', 'tx_timestamp')

    spending_by_txid = {}
    for tx in spending_txs:
        spending_by_txid.setdefault(tx['txid'], []).append(tx)

    gift_wallet_map = {}
    for gift in funded_gifts:
        funding = funding_by_address.get(gift.address)
        if not funding:
            continue

        spend_txs = spending_by_txid.get(funding['spending_txid'], [])
        for tx in spend_txs:
            wallet_hash = tx.get('wallet__wallet_hash')
            if not wallet_hash:
                continue

            key = (gift.id, wallet_hash)
            if key not in gift_wallet_map:
                gift_wallet_map[key] = (tx['tx_timestamp'], funding['spending_txid'], gift)

    if not gift_wallet_map:
        return

    gift_ids = [k[0] for k in gift_wallet_map]
    wallet_hashes = [k[1] for k in gift_wallet_map]

    all_claims = Claim.objects.filter(
        gift_id__in=gift_ids,
        wallet__wallet_hash__in=wallet_hashes
    ).select_related('wallet').order_by('-date_created')

    claim_map = {}
    for claim in all_claims:
        key = (claim.gift_id, claim.wallet.wallet_hash)
        if key not in claim_map:
            claim_map[key] = claim

    gifts_to_update = []
    claims_to_update = []

    for (gift_id, wallet_hash), (tx_timestamp, spending_txid, gift) in gift_wallet_map.items():
        claim = claim_map.get((gift_id, wallet_hash))
        if not claim:
            continue

        gift.date_claimed = tx_timestamp
        gift.claim_txid = spending_txid
        gifts_to_update.append(gift)
        claim.succeeded = True
        claims_to_update.append(claim)

    if gifts_to_update:
        Gift.objects.bulk_update(gifts_to_update, ['date_claimed', 'claim_txid'])
    if claims_to_update:
        Claim.objects.bulk_update(claims_to_update, ['succeeded'])
