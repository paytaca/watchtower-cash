"""
Builds and delivers live-activity updates for P2P Ramp orders.

The normalized payload produced here is the single shape consumed by both the
iOS ActivityKit widget and the Android ongoing notification (see the app's
`src/services/order-live-activity/model.js`). It is intentionally masked: no
amounts or counterparty names, only the order reference, status and deadline.
"""
import logging

from django.utils import timezone

from rampp2p import models

logger = logging.getLogger(__name__)

P2P_STAGE_COUNT = 5
P2P_STAGE_INDEX = {
    "SBM": 1,
    "CNF": 2,
    "ESCRW_PN": 2,
    "ESCRW": 3,
    "PD_PN": 3,
    "PD": 4,
    "RLS_PN": 4,
    "RLS": 5,
    "APL": 4,
    "RFN_PN": 4,
    "RFN": 5,
    "CNCL": 0,
}
P2P_TERMINAL = {
    "RLS": "success",
    "RFN": "failed",
    "CNCL": "cancelled",
}
# Statuses where `order.expires_at` is actually enforced: `Order.confirm` rejects
# an expired order and the cancel-expired-orders task only cancels these two.
# From escrow onward there is no deadline, and during an appeal the deadline is
# the appeal outcome, so counting down to `expires_at` there would be wrong.
P2P_EXPIRY_ENFORCED = {"SBM", "CNF"}
STATUS_LABELS = dict(models.StatusType.choices)


def _epoch_ms(value):
    if not value:
        return None
    return int(value.timestamp() * 1000)


def _progress(stage_index, stage_count):
    if not stage_count or stage_count <= 0:
        return 0.0
    ratio = max(stage_index, 0) / stage_count
    return round(min(max(ratio, 0.0), 1.0), 2)


def _capitalize(value=""):
    if not value:
        return ""
    return value[0].upper() + value[1:]


def build_order_live_activity(order, status=None):
    """Normalize an Order (+Status) into a lock-screen safe activity dict."""
    status = status or order.status
    status_code = str(getattr(status, "status", "") or "").upper()
    stage_index = P2P_STAGE_INDEX.get(status_code, 0)
    terminal_type = P2P_TERMINAL.get(status_code)

    trade_type = str(getattr(order, "trade_type", "") or "").upper()
    subtitle_parts = [f"Order #{order.id}"]
    if trade_type:
        subtitle_parts.append(_capitalize(trade_type.lower()))

    return {
        "id": f"p2p:{order.id}",
        "kind": "p2p",
        "orderId": order.id,
        "title": "P2P Ramp",
        "subtitle": " \u00b7 ".join(subtitle_parts),
        "statusCode": status_code,
        "statusLabel": STATUS_LABELS.get(status_code, status_code),
        "stageIndex": stage_index,
        "stageCount": P2P_STAGE_COUNT,
        "progress": _progress(stage_index, P2P_STAGE_COUNT),
        "countdownAt": (
            _epoch_ms(order.expires_at)
            if status_code in P2P_EXPIRY_ENFORCED
            else None
        ),
        "countdownLabel": "Expires in",
        "isTerminal": bool(terminal_type),
        "terminalType": terminal_type,
        "deepLink": f"paytaca://live-activity?kind=p2p&orderId={order.id}",
        "updatedAt": int(timezone.now().timestamp() * 1000),
    }


def is_order_member(order, wallet_hash):
    """Whether `wallet_hash` is a participant of `order` (seller, buyer or arbiter)."""
    if not wallet_hash:
        return False
    try:
        if order.is_seller(wallet_hash) or order.is_buyer(wallet_hash):
            return True
    except Exception:
        pass
    return bool(order.arbiter_id and order.arbiter and order.arbiter.wallet_hash == wallet_hash)


def update_order_live_activity(order, status=None):
    """
    Queue a push of the current order state to every registered live activity.

    The push itself does network I/O, so it runs in the
    `notifications.tasks.push_order_live_activity` Celery task instead of the
    status-save request. Safe to call unconditionally: it no-ops when the order
    has no registrations (i.e. no device currently tracks it).

    Returns:
        bool: whether a push was queued
    """
    from django.db import transaction

    from notifications.models import OrderLiveActivityToken
    from notifications.tasks import push_order_live_activity

    token_ids = list(
        OrderLiveActivityToken.objects.filter(order_id=order.id).values_list(
            "id", flat=True
        )
    )
    if not token_ids:
        return False

    activity = build_order_live_activity(order, status)

    def queue():
        try:
            push_order_live_activity.delay(activity, token_ids)
        except Exception as error:
            # A push is best-effort: a broker outage must not fail a status
            # change that has already been committed.
            logger.exception(f"Failed to queue order live activity push: {error}")

    # Push only once the status row is committed; a rolled-back transition must
    # not leave devices showing a status the server never stored.
    transaction.on_commit(queue)
    return True
