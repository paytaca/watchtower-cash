"""Keep canceled orders out of contract funding flows."""

from rampp2p.models import Status, StatusType


def order_is_canceled(order_id):
    # A late status update must not reopen a canceled funding flow.
    return Status.objects.filter(order_id=order_id, status=StatusType.CANCELED).exists()


def canceled_contract_payload():
    return {
        'success': False,
        'code': 'order_canceled',
        'error': 'This order is canceled. Do not fund its contract.',
    }
