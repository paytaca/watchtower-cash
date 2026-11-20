"""Preview or cancel explicitly reviewed, pre-escrow orders for one peer."""

from functools import partial
import json
import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_save
from django.utils import timezone

from rampp2p.models import (
    Contract, FeatureControl, Order, OrderMember, Peer, Status, StatusType, Transaction,
)

logger = logging.getLogger(__name__)
PRE_ESCROW_STATUSES = {StatusType.SUBMITTED, StatusType.CONFIRMED, StatusType.ESCROW_PENDING}


def notify_cancellation(order_id, wallets, is_cash_in, creator_wallet):
    """Deliver normal status hooks and cancellation notifications after commit."""
    try:
        canceled = Status.objects.select_related('order').filter(
            order_id=order_id, status=StatusType.CANCELED,
        ).order_by('-created_at', '-pk').first()
    except Exception:
        logger.exception('Failed to load committed cancellation of order %s', order_id)
        return
    if canceled is None:
        logger.warning('No committed cancellation found for order %s', order_id)
        return

    def best_effort(label, operation):
        try:
            operation()
        except Exception:
            logger.exception('Failed cancellation %s for order %s', label, order_id)

    def status_hooks():
        # bulk_create deliberately deferred this event until commit. Include
        # every normal receiver (Slack, Live Activity and future status hooks).
        for receiver, result in post_save.send_robust(
            sender=Status, instance=canceled, created=True, raw=False,
            using=canceled._state.db, update_fields=None,
        ):
            if isinstance(result, Exception):
                logger.error(
                    'Cancellation status receiver %s failed for order %s',
                    getattr(receiver, '__qualname__', repr(receiver)), order_id,
                    exc_info=(type(result), result, result.__traceback__),
                )

    def order_websocket():
        from rampp2p.serializers import StatusReadSerializer
        from rampp2p.utils import websocket
        websocket.send_order_update({
            'success': True, 'status': StatusReadSerializer(canceled).data,
        }, order_id)

    def cashin_websocket():
        from rampp2p.utils import websocket
        websocket.send_cashin_order_alert(
            {'type': 'ORDER_STATUS_UPDATED', 'order': order_id}, creator_wallet,
        )

    def push_notification():
        from rampp2p.utils.notifications import send_push_notification
        send_push_notification(
            wallets, 'Order #{} canceled. Do not fund its contract.'.format(order_id),
            extra={'order_id': order_id},
        )

    best_effort('status hooks', status_hooks)
    best_effort('order WebSocket', order_websocket)
    if is_cash_in:
        best_effort('cash-in WebSocket', cashin_websocket)
    best_effort('push notification', push_notification)


class Command(BaseCommand):
    help = ('Preview pending orders for a peer. Applying cancellation requires maintenance, '
            'explicit order IDs, and independent verification that they are unfunded. '
            'This command does not check the blockchain.')

    def add_arguments(self, parser):
        parser.add_argument('--peer-id', type=int, required=True)
        parser.add_argument('--peer-name', required=True, help='Must match the peer ID exactly.')
        parser.add_argument('--order-id', type=int, action='append', default=[])
        parser.add_argument('--apply', action='store_true', help='Default is a read-only preview.')
        parser.add_argument(
            '--verified-unfunded', action='store_true',
            help='Attest that every selected order and its known contract addresses were '
                 'independently checked for funding, including pending transactions.',
        )
        parser.add_argument(
            '--verified-contract-address', action='append', default=[],
            help='Repeat for each current contract address checked as unfunded. '
                 'A newly changed address requires another review.',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        requested_ids = set(options['order_id'])
        verified_addresses = set(options['verified_contract_address'])
        if apply and (not requested_ids or not options['verified_unfunded']):
            raise CommandError('--apply requires explicit --order-id values and --verified-unfunded.')

        rows, canceled_ids = [], []
        with transaction.atomic():
            try:
                peer = Peer.objects.get(pk=options['peer_id'], name=options['peer_name'])
            except Peer.DoesNotExist:
                raise CommandError('Peer ID and name do not match an existing account.')
            if apply and not FeatureControl.objects.filter(
                name=FeatureControl.Type.P2P_MAINTENANCE, is_enabled=True,
            ).exists():
                raise CommandError('Enable P2P_MAINTENANCE before applying incident cancellations.')

            queryset = Order.objects.filter(owner_id=peer.pk).order_by('pk')
            if requested_ids:
                queryset = queryset.filter(pk__in=requested_ids)
            if apply:
                queryset = queryset.select_for_update()
            orders = list(queryset)
            if requested_ids - {order.pk for order in orders}:
                raise CommandError('Every selected order must exist and have been created by this peer.')

            for order in orders:
                history = list(Status.objects.filter(order_id=order.pk).order_by(
                    '-created_at', '-pk',
                ).values_list('status', flat=True))
                contracts = Contract.objects.filter(order_id=order.pk)
                if apply:
                    contracts = contracts.select_for_update()
                contract = contracts.first()
                address = contract.address if contract else None
                reason = None
                if history and history[0] == StatusType.CANCELED:
                    reason = 'already_canceled'
                elif not history or any(code not in PRE_ESCROW_STATUSES for code in history):
                    reason = 'missing_status_or_escrow_terminal_history'
                elif Transaction.objects.filter(contract__order_id=order.pk).filter(
                    Q(valid=True) | (Q(txid__isnull=False) & ~Q(txid='')),
                ).exists():
                    reason = 'recorded_transaction_requires_investigation'
                rows.append({
                    'order_id': order.pk,
                    'latest_status': history[0] if history else None,
                    'contract_address': address,
                    'skip_reason': reason,
                    'independent_funding_verification_required': reason is None,
                })

            if apply:
                unsafe = [row['order_id'] for row in rows
                          if row['skip_reason'] not in (None, 'already_canceled')]
                unverified = [row['order_id'] for row in rows
                              if row['skip_reason'] is None and row['contract_address']
                              and row['contract_address'] not in verified_addresses]
                if unsafe or unverified:
                    raise CommandError(
                        'No orders changed. Ineligible order IDs: {}. '
                        'Unverified current contract addresses on order IDs: {}.'.format(
                            unsafe, unverified,
                        )
                    )
                eligible_ids = {row['order_id'] for row in rows if row['skip_reason'] is None}
                for order in orders:
                    if order.pk not in eligible_ids:
                        continue
                    # Defer normal status signals and participant notifications
                    # until commit; do not run services for rolled-back rows.
                    Status.objects.bulk_create([Status(
                        order_id=order.pk, status=StatusType.CANCELED,
                        created_by='SYSTEM_AUTOMATED',
                    )])
                    OrderMember.objects.filter(order_id=order.pk).update(read_at=timezone.now())
                    wallets = sorted({order.owner.wallet_hash, order.ad_snapshot.ad.owner.wallet_hash})
                    transaction.on_commit(partial(
                        notify_cancellation, order.pk, wallets,
                        order.is_cash_in, order.owner.wallet_hash,
                    ))
                    canceled_ids.append(order.pk)

        self.stdout.write(json.dumps({
            'dry_run': not apply, 'peer_id': peer.pk, 'peer_name': peer.name,
            'canceled_order_ids': canceled_ids, 'orders': rows,
            'limitations': [
                'No live blockchain checks were performed.',
                'A missing escrow record does not establish that a contract is unfunded.',
                'Cancellation cannot invalidate addresses already obtained by clients.',
            ],
        }, indent=2))
