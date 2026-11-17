import csv
import json
from datetime import timedelta, timezone as datetime_timezone

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Prefetch, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from rampp2p.models import Contract, Order, Status
from rampp2p.order_audit import audit_order, burst_order_ids


def parse_bound(value):
    try:
        result = parse_datetime(value)
    except (ValueError, TypeError):
        result = None
    if result is None:
        raise CommandError('Use an ISO datetime, e.g. 2026-11-17T00:00:00+08:00')
    if timezone.is_naive(result):
        result = timezone.make_aware(result, datetime_timezone.utc)
    return result


class Command(BaseCommand):
    help = ('Read-only review of recent P2P orders. Flags do not prove abuse; '
            'funding evidence is from the database, not a live blockchain check.')

    def add_arguments(self, parser):
        window = parser.add_mutually_exclusive_group()
        window.add_argument('--days', type=int, help='Look back N days (default: 7).')
        window.add_argument('--since', help='Inclusive ISO datetime; naive values mean UTC.')
        parser.add_argument('--until', help='Exclusive ISO datetime (default: now).')
        parser.add_argument('--wallet-hash', action='append', default=[],
                            help='Filter by creator, ad owner, or arbiter; repeatable.')
        parser.add_argument('--order-id', type=int, action='append', default=[])
        parser.add_argument('--format', choices=['json', 'csv'], default='csv')
        parser.add_argument('--flagged-only', action='store_true')
        parser.add_argument('--burst-count', type=int, default=5)
        parser.add_argument('--burst-minutes', type=int, default=5)

    def handle(self, *args, **options):
        days = options['days'] if options['days'] is not None else 7
        if days < 1 or options['burst_count'] < 2 or options['burst_minutes'] < 1:
            raise CommandError('days/minutes must be positive; burst-count must be at least 2.')
        until = parse_bound(options['until']) if options['until'] else timezone.now()
        since = parse_bound(options['since']) if options['since'] else until - timedelta(days=days)
        if since >= until:
            raise CommandError('--since must precede --until.')

        queryset = Order.objects.filter(created_at__gte=since, created_at__lt=until)
        if options['wallet_hash']:
            wallets = options['wallet_hash']
            queryset = queryset.filter(
                Q(owner__wallet_hash__in=wallets)
                | Q(ad_snapshot__ad__owner__wallet_hash__in=wallets)
                | Q(arbiter__wallet_hash__in=wallets)
            )
        if options['order_id']:
            queryset = queryset.filter(pk__in=options['order_id'])
        orders = list(queryset.select_related(
            'owner', 'arbiter', 'ad_snapshot__ad__owner', 'contract',
        ).prefetch_related(
            Prefetch('status_set', queryset=Status.objects.order_by('created_at', 'pk'),
                     to_attr='audit_statuses'),
            'contract__members', 'contract__transaction_set',
        ).order_by('created_at', 'pk'))
        bursts = burst_order_ids(orders, options['burst_count'], options['burst_minutes'])
        rows = []
        for order in orders:
            try:
                contract = order.contract
            except Contract.DoesNotExist:
                contract = None
            rows.append(audit_order(
                order, contract, order.audit_statuses,
                list(contract.members.all()) if contract else [],
                list(contract.transaction_set.all()) if contract else [],
                burst=order.pk in bursts,
            ))
        flagged = sum(bool(row['review_flags']) for row in rows)
        if options['flagged_only']:
            rows = [row for row in rows if row['review_flags']]

        if options['format'] == 'json':
            self.stdout.write(json.dumps({
                'since': since.isoformat(), 'until': until.isoformat(),
                'orders_scanned': len(orders), 'orders_flagged': flagged,
                'limitations': [
                    'Flags require manual review; matching keys do not prove consent.',
                    'Profile comparisons use current data, not historical identity records.',
                    'Recorded contract members are not independently verified against the on-chain script.',
                    'No live blockchain checks; absent transactions do not prove an unfunded address.',
                    'Burst detection covers only the selected orders and time range.',
                ],
                'orders': rows,
            }, indent=2))
        else:
            fields = [
                'order_id', 'tracking_id', 'created_at', 'order_trade_type',
                'ad_id', 'ad_trade_type', 'trade_amount_sats', 'is_cash_in',
                'latest_status', 'funding_evidence', 'review_flags',
                'contract_id', 'contract_address', 'creator', 'ad_owner',
                'seller', 'buyer', 'arbiter', 'contract_members', 'statuses', 'transactions',
            ]
            writer = csv.DictWriter(self.stdout, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    key: self.csv_cell(json.dumps(value) if isinstance(value, (dict, list)) else value)
                    for key, value in row.items()
                })
        self.stderr.write(
            'Scanned {}; flagged {} for manual review. No records changed. '
            'No live blockchain checks; no recorded funding does not mean unfunded. '
            'Profile/key comparisons use current account data, not historical proof of consent.'
            .format(len(orders), flagged)
        )

    @staticmethod
    def csv_cell(value):
        # User-controlled tracking IDs can otherwise execute spreadsheet formulas.
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
            return "'" + value
        return value
