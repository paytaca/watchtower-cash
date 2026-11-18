"""Preview or cancel explicitly reviewed, pre-escrow orders for one peer."""

from functools import partial
import json
import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from rampp2p.models import (
    Contract, FeatureControl, Order, OrderMember, Peer, Status, StatusType, Transaction,
)

logger = logging.getLogger(__name__)
PRE_ESCROW_STATUSES = {StatusType.SUBMITTED, StatusType.CONFIRMED, StatusType.ESCROW_PENDING}


def notify_cancellation(order_id, wallets, is_cash_in, creator_wallet):
    # Publish only after the cancellation commits. Preserve the database change
    # if a notification service is unavailable.
    try:
        from rampp2p.serializers import StatusReadSerializer
        from rampp2p.utils import websocket
        from rampp2p.utils.notifications import send_push_notification

        canceled = Status.objects.filter(
            order_id=order_id, status=StatusType.CANCELED,
        ).order_by('-created_at', '-pk').first()
        websocket.send_order_update({
            'success': True, 'status': StatusReadSerializer(canceled).data,
        }, order_id)
        if is_cash_in:
            websocket.send_cashin_order_alert(
                {'type': 'ORDER_STATUS_UPDATED', 'order': order_id}, creator_wallet,
            )
        send_push_notification(
            wallets, 'Order #{} canceled. Do not fund its contract.'.format(order_id),
            extra={'order_id': order_id},
        )
    except Exception:
        logger.exception('Failed to notify cancellation of order %s', order_id)


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
                    # Avoid synchronous signal side effects before commit;
                    # notify participants explicitly through on_commit below.
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
