"""Read-only review heuristics. Flags are leads, never proof of impersonation."""

from collections import defaultdict, deque
from datetime import timedelta

import ecdsa


def canonical_key(value):
    """Validate a secp256k1 curve point and return its compressed encoding."""
    try:
        key = ecdsa.VerifyingKey.from_string(
            bytes.fromhex(value), curve=ecdsa.SECP256k1
        )
    except (ValueError, TypeError, ecdsa.errors.MalformedPointError) as error:
        raise ValueError('Invalid secp256k1 public key') from error
    return key.to_string('compressed')


def burst_order_ids(orders, count, minutes):
    """Flag creator bursts, sorting input by creation time and primary key."""
    windows = defaultdict(deque)
    flagged = set()
    interval = timedelta(minutes=minutes)
    for order in sorted(orders, key=lambda item: (item.created_at, item.pk)):
        window = windows[order.owner_id]
        while window and order.created_at - window[0].created_at > interval:
            window.popleft()
        window.append(order)
        if len(window) == count:
            flagged.update(item.pk for item in window)
        elif len(window) > count:
            # Earlier members were flagged when the threshold was reached.
            flagged.add(order.pk)
    return flagged


def account_data(account):
    if account is None:
        return None
    return {
        'id': account.pk, 'name': account.name,
        'wallet_hash': account.wallet_hash,
        'public_key': account.public_key, 'address': account.address,
    }


def audit_order(order, contract, statuses, members, transactions, burst=False):
    """Review an order, sorting status history by creation time and primary key."""
    statuses = sorted(statuses, key=lambda item: (item.created_at, item.pk))
    ad_owner = order.ad_snapshot.ad.owner
    seller, buyer = (ad_owner, order.owner)
    if order.ad_snapshot.trade_type == 'BUY':
        seller, buyer = buyer, seller
    parties = {'SELLER': seller, 'BUYER': buyer, 'ARBITER': order.arbiter}
    flags = []
    if burst:
        flags.append('RAPID_ORDER_CREATION')
    if order.trade_amount is None or order.trade_amount <= 0:
        flags.append('NONPOSITIVE_OR_MISSING_AMOUNT')
    submitted = [s for s in statuses if s.status == 'SBM']
    if not submitted:
        flags.append('MISSING_SUBMITTED_STATUS')
    elif submitted[0].created_by != order.owner.wallet_hash:
        flags.append('SUBMITTED_ACTOR_DIFFERS_FROM_CREATOR')
    allowed = {p.wallet_hash for p in parties.values() if p is not None}
    if any(s.created_by and s.created_by not in allowed for s in statuses):
        flags.append('STATUS_ACTOR_OUTSIDE_CURRENT_PARTICIPANTS')

    if contract:
        if not contract.address:
            flags.append('CONTRACT_ADDRESS_MISSING')
        for role, account in parties.items():
            recorded = [m for m in members if m.member_type == role]
            if len(recorded) != 1:
                flags.append(role + '_CONTRACT_MEMBER_MISSING_OR_DUPLICATE')
                continue
            member = recorded[0]
            if account is None or member.member_ref_id != account.pk:
                flags.append(role + '_CONTRACT_ACCOUNT_MISMATCH')
                continue
            try:
                if canonical_key(member.pubkey) != canonical_key(account.public_key):
                    flags.append(role + '_CONTRACT_KEY_DIFFERS_FROM_CURRENT_PROFILE')
            except (ValueError, TypeError):
                flags.append(role + '_INVALID_KEY_ENCODING')
            if member.address != account.address:
                flags.append(role + '_CONTRACT_ADDRESS_DIFFERS_FROM_CURRENT_PROFILE')

    # No recorded escrow is NOT evidence that an address is unfunded.
    recorded_txids = [t for t in transactions if t.txid]
    if any(t.action == 'ESCROW' and t.valid for t in recorded_txids):
        funding = 'VALIDATED_ESCROW_RECORDED'
    elif recorded_txids:
        funding = 'TRANSACTION_RECORDED_REVIEW_ON_CHAIN'
    elif any(s.status in {'ESCRW', 'PD_PN', 'PD', 'APL', 'RLS_PN', 'RLS', 'RFN_PN', 'RFN'}
             for s in statuses):
        funding = 'POST_ESCROW_STATUS_REVIEW_ON_CHAIN'
    else:
        funding = 'NO_FUNDING_RECORDED_NOT_VERIFIED_ON_CHAIN'

    return {
        'order_id': order.pk, 'tracking_id': order.tracking_id,
        'created_at': order.created_at.isoformat(),
        'order_trade_type': 'SELL' if order.ad_snapshot.trade_type == 'BUY' else 'BUY',
        'ad_id': order.ad_snapshot.ad_id, 'ad_trade_type': order.ad_snapshot.trade_type,
        'trade_amount_sats': order.trade_amount, 'is_cash_in': order.is_cash_in,
        'creator': account_data(order.owner), 'ad_owner': account_data(ad_owner),
        'seller': account_data(seller), 'buyer': account_data(buyer),
        'arbiter': account_data(order.arbiter),
        'latest_status': statuses[-1].status if statuses else None,
        'contract_id': contract.pk if contract else None,
        'contract_address': contract.address if contract else None,
        'contract_members': [{
            'role': m.member_type, 'account_id': m.member_ref_id,
            'public_key': m.pubkey, 'address': m.address,
        } for m in members],
        'statuses': [{
            'status': s.status, 'created_at': s.created_at.isoformat(),
            'created_by': s.created_by,
        } for s in statuses],
        'transactions': [{
            'action': t.action, 'txid': t.txid, 'valid': t.valid,
        } for t in transactions],
        'funding_evidence': funding, 'review_flags': flags,
    }
