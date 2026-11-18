"""Authorization for private order data, using typed account identities."""

from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from rampp2p.models import Arbiter, Peer


def order_participant_filter(user):
    if getattr(user, 'pk', None) is None:
        return Q(pk__in=[])
    if isinstance(user, Peer):
        return Q(owner_id=user.pk) | Q(ad_snapshot__ad__owner_id=user.pk)
    if isinstance(user, Arbiter):
        return Q(arbiter_id=user.pk)
    return Q(pk__in=[])


def require_order_participant(order, user, allow_arbiter=True):
    if isinstance(user, Peer) and user.pk in (order.owner_id, order.ad_snapshot.ad.owner_id):
        return
    if (allow_arbiter and isinstance(user, Arbiter)
            and user.pk is not None and order.arbiter_id == user.pk):
        return
    raise PermissionDenied('Only order participants may access this order.')


def require_order_ad_owner(order, user):
    if isinstance(user, Peer) and user.pk == order.ad_snapshot.ad.owner_id:
        return
    raise PermissionDenied('Only the ad owner may confirm this order.')
