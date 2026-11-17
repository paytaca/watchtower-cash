"""Management-command coverage using real ORM relations and synthetic records."""

import csv
import io
import json
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from rampp2p.models import (
    Ad, AdSnapshot, Arbiter, Contract, ContractMember, CryptoCurrency,
    FiatCurrency, Order, Peer, Status, Transaction,
)
from rampp2p.test_order_audit import KEY


class AuditP2POrdersCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.now = timezone.now() - timedelta(hours=1)
        cls.creator = Peer.objects.create(
            name='Audit creator', wallet_hash='audit-creator', public_key=KEY,
            address='synthetic-creator-address',
        )
        cls.ad_owner = Peer.objects.create(
            name='Audit ad owner', wallet_hash='audit-ad-owner', public_key=KEY,
            address='synthetic-ad-owner-address',
        )
        cls.arbiter = Arbiter.objects.create(
            name='Audit arbiter', wallet_hash='audit-arbiter', public_key=KEY,
            address='synthetic-arbiter-address',
        )
        fiat = FiatCurrency.objects.create(name='Audit fiat', symbol='TST')
        crypto = CryptoCurrency.objects.create(name='Audit crypto', symbol='TESTBCH')
        # Only fixture creation is mocked for external notifications. The command
        # itself uses real models, joins, prefetches and database queries.
        with patch('rampp2p.signals.AdSummaryMessage.send_safe'):
            ad = Ad.objects.create(
                owner=cls.ad_owner, trade_type='BUY', price_type='FIXED',
                fiat_currency=fiat, crypto_currency=crypto,
            )
        snapshot = AdSnapshot.objects.create(
            ad=ad, trade_type='BUY', price_type='FIXED', fiat_currency=fiat,
            crypto_currency=crypto, appeal_cooldown_choice=60,
        )
        cls.first = Order.objects.create(
            owner=cls.creator, arbiter=cls.arbiter, ad_snapshot=snapshot,
            tracking_id='audit-first', trade_amount=10000, is_cash_in=False,
        )
        cls.second = Order.objects.create(
            owner=cls.creator, ad_snapshot=snapshot, tracking_id='audit-second',
            trade_amount=20000, is_cash_in=True,
        )
        cls.old = Order.objects.create(
            owner=cls.creator, ad_snapshot=snapshot, tracking_id='audit-old',
            trade_amount=30000,
        )
        for order, offset in ((cls.first, timedelta()), (cls.second, timedelta(minutes=1)),
                              (cls.old, -timedelta(days=10))):
            Order.objects.filter(pk=order.pk).update(created_at=cls.now + offset)
        # bulk_create avoids real Slack/push/worker activity during fixtures.
        Status.objects.bulk_create([
            Status(order=order, status=code, created_by=cls.creator.wallet_hash)
            for order in (cls.first, cls.second) for code in ('SBM', 'CNF')
        ])
        cls.contract = Contract.objects.create(order=cls.first, address='synthetic-contract')
        ContractMember.objects.bulk_create([
            ContractMember(contract=cls.contract, member_type=role, member_ref_id=account.pk,
                           pubkey=KEY, address=account.address)
            for role, account in (
                ('SELLER', cls.creator), ('BUYER', cls.ad_owner), ('ARBITER', cls.arbiter),
            )
        ])
        Transaction.objects.create(
            contract=cls.contract, action='ESCROW', txid='synthetic-escrow-tx', valid=True,
        )

    def run_audit(self, **options):
        stdout, stderr = io.StringIO(), io.StringIO()
        defaults = {
            'since': (self.now - timedelta(minutes=1)).isoformat(),
            'until': (self.now + timedelta(minutes=2)).isoformat(),
            'format': 'json',
        }
        defaults.update(options)
        call_command('audit_p2p_orders', stdout=stdout, stderr=stderr, **defaults)
        return stdout.getvalue(), stderr.getvalue()

    def test_json_uses_real_prefetched_relations_and_handles_missing_contract(self):
        report = json.loads(self.run_audit()[0])
        self.assertEqual(report['orders_scanned'], 2)
        self.assertEqual(report['orders_flagged'], 0)
        first, second = report['orders']
        self.assertEqual(first['order_id'], self.first.pk)
        self.assertEqual(first['seller']['id'], self.creator.pk)
        self.assertEqual(first['contract_id'], self.contract.pk)
        self.assertEqual(len(first['contract_members']), 3)
        self.assertEqual(first['transactions'][0]['txid'], 'synthetic-escrow-tx')
        self.assertEqual(first['funding_evidence'], 'VALIDATED_ESCROW_RECORDED')
        self.assertEqual([s['status'] for s in first['statuses']], ['SBM', 'CNF'])
        self.assertIsNone(second['contract_id'])
        self.assertEqual(second['funding_evidence'], 'NO_FUNDING_RECORDED_NOT_VERIFIED_ON_CHAIN')

    def test_wallet_and_order_id_filters(self):
        for account, expected in (
            (self.creator, [self.first.pk, self.second.pk]),
            (self.ad_owner, [self.first.pk, self.second.pk]),
            (self.arbiter, [self.first.pk]),
        ):
            with self.subTest(account=account.wallet_hash):
                report = json.loads(self.run_audit(wallet_hash=[account.wallet_hash])[0])
                self.assertEqual([r['order_id'] for r in report['orders']], expected)
        report = json.loads(self.run_audit(order_id=[self.second.pk])[0])
        self.assertEqual([r['order_id'] for r in report['orders']], [self.second.pk])
        report = json.loads(self.run_audit(wallet_hash=['absent-account'])[0])
        self.assertEqual(report['orders'], [])

    def test_time_bounds_are_inclusive_since_and_exclusive_until(self):
        report = json.loads(self.run_audit(
            since=self.now.isoformat(), until=(self.now + timedelta(minutes=1)).isoformat(),
        )[0])
        self.assertEqual([r['order_id'] for r in report['orders']], [self.first.pk])

    def test_flagged_only_finds_invalid_curve_point(self):
        ContractMember.objects.filter(contract=self.contract, member_type='SELLER').update(
            pubkey=KEY[2:] + '00' * 32,
        )
        report = json.loads(self.run_audit(flagged_only=True)[0])
        self.assertEqual(report['orders_scanned'], 2)
        self.assertEqual([r['order_id'] for r in report['orders']], [self.first.pk])
        self.assertIn('SELLER_INVALID_KEY_ENCODING', report['orders'][0]['review_flags'])

    def test_csv_contains_parseable_details_and_escapes_formulas(self):
        Order.objects.filter(pk=self.first.pk).update(tracking_id='=SUM(1,2)')
        rows = list(csv.DictReader(io.StringIO(self.run_audit(format='csv')[0])))
        self.assertEqual(len(rows), 2)
        first = next(r for r in rows if r['order_id'] == str(self.first.pk))
        self.assertEqual(first['tracking_id'], "'=SUM(1,2)")
        self.assertEqual(json.loads(first['statuses'])[0]['status'], 'SBM')
        self.assertEqual(len(json.loads(first['contract_members'])), 3)

    def test_command_runs_selects_only_and_changes_no_records(self):
        models = (Peer, Arbiter, Ad, AdSnapshot, Order, Status, Contract, ContractMember, Transaction)
        before = {model: list(model.objects.order_by('pk').values()) for model in models}
        with CaptureQueriesContext(connection) as queries:
            self.run_audit()
        self.assertTrue(queries.captured_queries)
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in queries))
        after = {model: list(model.objects.order_by('pk').values()) for model in models}
        self.assertEqual(before, after)

    def test_bursts_are_detected_through_command(self):
        report = json.loads(self.run_audit(burst_count=2)[0])
        self.assertEqual(report['orders_flagged'], 2)
        self.assertTrue(all('RAPID_ORDER_CREATION' in r['review_flags'] for r in report['orders']))

    def test_invalid_bounds_fail_before_querying(self):
        for options in ({'since': 'invalid'}, {'since': self.now.isoformat(), 'until': self.now.isoformat()},
                        {'burst_count': 1}):
            with self.subTest(options=options), self.assertNumQueries(0), self.assertRaises(CommandError):
                self.run_audit(**options)
