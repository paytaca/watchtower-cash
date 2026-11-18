import io
import json
from unittest.mock import Mock, patch

from django.core.management import call_command, CommandError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIRequestFactory, force_authenticate

from rampp2p.models import (
    Ad, AdSnapshot, Contract, CryptoCurrency, FeatureControl, FiatCurrency,
    Order, OrderMember, Peer, Status, StatusType, Transaction,
)
from rampp2p.tasks.task_contract import contract_handler
from rampp2p.views.view_contract import ContractViewSet


class CancellationFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.creator = Peer.objects.create(
            name='Synthetic creator', wallet_hash='synthetic-creator',
            public_key='synthetic-key', address='synthetic-address',
        )
        cls.seller = Peer.objects.create(
            name='Synthetic seller', wallet_hash='synthetic-seller',
            public_key='synthetic-key', address='synthetic-address',
        )
        fiat = FiatCurrency.objects.create(name='Synthetic fiat', symbol='TST')
        crypto = CryptoCurrency.objects.create(name='Synthetic crypto', symbol='TESTBCH')
        with patch('rampp2p.signals.AdSummaryMessage.send_safe'):
            ad = Ad.objects.create(
                owner=cls.seller, trade_type='SELL', price_type='FIXED',
                fiat_currency=fiat, crypto_currency=crypto,
            )
        cls.snapshot = AdSnapshot.objects.create(
            ad=ad, trade_type='SELL', price_type='FIXED', fiat_currency=fiat,
            crypto_currency=crypto, appeal_cooldown_choice=60,
        )
        cls.order = Order.objects.create(
            owner=cls.creator, ad_snapshot=cls.snapshot, trade_amount=10000,
        )
        cls.contract = Contract.objects.create(order=cls.order, address='synthetic-contract')
        Status.objects.bulk_create([Status(order=cls.order, status=StatusType.CONFIRMED)])
        cls.member = OrderMember.objects.create(order=cls.order, peer=cls.seller, type='SELLER')
        cls.maintenance = FeatureControl.objects.create(name='P2P_MAINTENANCE', is_enabled=False)

    def add_status(self, code, order=None):
        Status.objects.bulk_create([Status(order=order or self.order, status=code)])


class CanceledContractAccessTests(CancellationFixtures):
    def setUp(self):
        self.factory = APIRequestFactory()
        permission = patch(
            'authentication.permissions.RampP2PIsAuthenticated.has_permission', return_value=True,
        )
        permission.start()
        self.addCleanup(permission.stop)

    def retrieve(self, action):
        request = self.factory.get('/unused/')
        force_authenticate(request, user=self.seller)
        pk = self.contract.pk if action == 'retrieve' else self.order.pk
        return ContractViewSet.as_view({'get': action})(request, pk=pk)

    def test_both_contract_read_endpoints_withhold_canceled_contracts(self):
        self.add_status(StatusType.CANCELED)
        for action in ('retrieve', 'retrieve_by_order'):
            with self.subTest(action=action), patch(
                'rampp2p.views.view_contract.serializers.ContractSerializer',
            ) as serialize:
                response = self.retrieve(action)
                self.assertEqual(response.status_code, 410)
                self.assertEqual(response.data['code'], 'order_canceled')
                self.assertNotIn('address', response.data)
                self.assertNotIn('members', response.data)
                self.assertEqual(response['Cache-Control'], 'no-store')
                serialize.assert_not_called()
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.address, 'synthetic-contract')

    def test_live_and_funded_orders_keep_contract_access(self):
        for code in (StatusType.CONFIRMED, StatusType.ESCROWED, StatusType.RELEASED):
            self.add_status(code)
            for action in ('retrieve', 'retrieve_by_order'):
                with self.subTest(code=code, action=action), patch(
                    'rampp2p.views.view_contract.serializers.ContractSerializer',
                    return_value=Mock(data={'address': self.contract.address}),
                ):
                    response = self.retrieve(action)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.data['address'], self.contract.address)
                    self.assertEqual(response['Cache-Control'], 'no-store')

    def test_missing_contract_still_returns_404(self):
        Contract.objects.filter(pk=self.contract.pk).delete()
        for action in ('retrieve', 'retrieve_by_order'):
            with self.subTest(action=action):
                self.assertEqual(self.retrieve(action).status_code, 404)

    def test_canceled_order_cannot_regenerate_a_contract_even_with_force(self):
        self.add_status(StatusType.CANCELED)
        FeatureControl.objects.create(name='ORDER_ESCROW', is_enabled=True)
        request = self.factory.post('/unused/', {
            'order_id': self.order.pk, 'arbiter_id': 1, 'force': True,
        }, format='json')
        force_authenticate(request, user=self.seller)
        with patch('rampp2p.views.view_contract.utils.is_min_version_compatible', return_value=True), \
             patch('rampp2p.views.view_contract.create_contract') as generate:
            response = ContractViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 400)
        generate.assert_not_called()
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.address, 'synthetic-contract')

    def test_cancellation_is_respected_when_status_timestamps_tie(self):
        self.add_status(StatusType.CANCELED)
        timestamp = self.order.created_at
        Status.objects.filter(order=self.order).update(created_at=timestamp)
        self.assertEqual(self.retrieve('retrieve').status_code, 410)

    def test_late_status_event_cannot_reopen_contract_access(self):
        self.add_status(StatusType.CANCELED)
        self.add_status(StatusType.CONFIRMED)
        for action in ('retrieve', 'retrieve_by_order'):
            with self.subTest(action=action):
                self.assertEqual(self.retrieve(action).status_code, 410)

    def test_cancellation_during_contract_setup_stops_generation(self):
        FeatureControl.objects.create(name='ORDER_ESCROW', is_enabled=True)
        request = self.factory.post('/unused/', {
            'order_id': self.order.pk, 'arbiter_id': 1,
        }, format='json')
        force_authenticate(request, user=self.seller)
        arbiter = Mock()
        arbiter.fiat_currencies.filter.return_value.exists.return_value = True

        def cancel_during_setup(*args):
            self.add_status(StatusType.CANCELED)
            return {}

        with patch('rampp2p.views.view_contract.utils.is_min_version_compatible', return_value=True), \
             patch('rampp2p.views.view_contract.models.Arbiter.objects.get', return_value=arbiter), \
             patch.object(ContractViewSet, '_get_contract_params', side_effect=cancel_during_setup), \
             patch('rampp2p.views.view_contract.create_contract') as generate:
            response = ContractViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 400)
        generate.assert_not_called()
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.address, 'synthetic-contract')


class CanceledContractCallbackTests(CancellationFixtures):
    def run_callback(self, subscribe=None):
        response = {'result': {'success': 'true', 'contract_address': 'generated-address'}}
        with patch('rampp2p.tasks.task_contract.send_order_update') as send, \
             patch('rampp2p.tasks.task_contract.save_subscription', side_effect=subscribe) as subscription:
            contract_handler.run(response, order_id=self.order.pk)
        return send, subscription

    def test_queued_callback_cannot_publish_or_save_address_after_cancellation(self):
        self.add_status(StatusType.CANCELED)
        send, subscription = self.run_callback()
        subscription.assert_not_called()
        payload, order_id = send.call_args[0]
        self.assertEqual(order_id, self.order.pk)
        self.assertEqual(payload['code'], 'order_canceled')
        self.assertNotIn('contract_address', payload)
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.address, 'synthetic-contract')

    def test_cancellation_during_callback_withholds_websocket_address(self):
        def cancel_during_subscription(*args):
            self.add_status(StatusType.CANCELED)
            return True

        send, _ = self.run_callback(subscribe=cancel_during_subscription)
        payload = send.call_args[0][0]
        self.assertEqual(payload['code'], 'order_canceled')
        self.assertNotIn('contract_address', payload)

    def test_active_callback_still_saves_and_publishes_address(self):
        send, subscription = self.run_callback(subscribe=lambda *args: True)
        subscription.assert_called_once_with('generated-address', self.contract.pk)
        self.assertEqual(send.call_args[0][0]['contract_address'], 'generated-address')
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.address, 'generated-address')


class CancelPendingOrdersCommandTests(CancellationFixtures):
    def setUp(self):
        FeatureControl.objects.filter(pk=self.maintenance.pk).update(is_enabled=True)
        notification = patch(
            'rampp2p.management.commands.cancel_pending_p2p_orders.notify_cancellation',
        )
        self.notify = notification.start()
        self.addCleanup(notification.stop)

    def run_command(self, **options):
        output = io.StringIO()
        arguments = {'peer_id': self.creator.pk, 'peer_name': self.creator.name}
        arguments.update(options)
        call_command('cancel_pending_p2p_orders', stdout=output, **arguments)
        return json.loads(output.getvalue())

    def apply(self, **options):
        arguments = {
            'apply': True, 'order_id': [self.order.pk], 'verified_unfunded': True,
            'verified_contract_address': [self.contract.address],
        }
        arguments.update(options)
        return self.run_command(**arguments)

    def test_default_preview_performs_no_record_writes(self):
        before = list(Status.objects.values())
        with CaptureQueriesContext(connection) as queries:
            result = self.run_command()
        self.assertTrue(result['dry_run'])
        self.assertEqual(result['canceled_order_ids'], [])
        self.assertEqual(result['orders'][0]['contract_address'], self.contract.address)
        self.assertEqual(list(Status.objects.values()), before)
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(
            ('INSERT', 'UPDATE', 'DELETE'),
        ) for q in queries))
        self.notify.assert_not_called()

    def test_apply_requires_explicit_ids_funding_review_and_maintenance(self):
        for options in ({'order_id': []}, {'verified_unfunded': False}):
            with self.subTest(options=options), self.assertRaises(CommandError):
                self.apply(**options)
        FeatureControl.objects.filter(pk=self.maintenance.pk).update(is_enabled=False)
        with self.assertRaisesMessage(CommandError, 'P2P_MAINTENANCE'):
            self.apply()
        self.assertEqual(Status.objects.filter(order=self.order).count(), 1)

    def test_peer_identity_and_order_scope_are_verified(self):
        for options in ({'peer_name': 'wrong-name'}, {'order_id': [999999]},
                        {'peer_id': self.seller.pk, 'peer_name': self.seller.name}):
            with self.subTest(options=options), self.assertRaises(CommandError):
                self.apply(**options)

    def test_generated_address_requires_exact_external_review(self):
        for addresses in ([], ['old-address']):
            with self.subTest(addresses=addresses), self.assertRaisesMessage(
                CommandError, 'Unverified current contract addresses',
            ):
                self.apply(verified_contract_address=addresses)
        self.assertEqual(Status.objects.filter(order=self.order).count(), 1)

    def test_applies_cancellation_without_changing_contract_or_ad(self):
        before_ad = Ad.objects.values().get(pk=self.snapshot.ad_id)
        with patch('rampp2p.management.commands.cancel_pending_p2p_orders.transaction.on_commit') as commit:
            result = self.apply()
        self.assertEqual(result['canceled_order_ids'], [self.order.pk])
        latest = Status.objects.filter(order=self.order).order_by('-created_at', '-pk').first()
        self.assertEqual(latest.status, StatusType.CANCELED)
        self.assertEqual(latest.created_by, 'SYSTEM_AUTOMATED')
        self.contract.refresh_from_db()
        self.member.refresh_from_db()
        self.assertEqual(self.contract.address, 'synthetic-contract')
        self.assertIsNotNone(self.member.read_at)
        self.assertEqual(Ad.objects.values().get(pk=self.snapshot.ad_id), before_ad)
        self.notify.assert_not_called()
        callback = commit.call_args[0][0]
        callback()
        self.notify.assert_called_once_with(
            self.order.pk, ['synthetic-creator', 'synthetic-seller'], False, 'synthetic-creator',
        )

    def test_orders_without_a_contract_can_be_canceled_after_review(self):
        Contract.objects.filter(pk=self.contract.pk).delete()
        result = self.apply(verified_contract_address=[])
        self.assertEqual(result['canceled_order_ids'], [self.order.pk])

    def test_all_pre_escrow_statuses_are_eligible_for_review(self):
        for code in (StatusType.SUBMITTED, StatusType.CONFIRMED, StatusType.ESCROW_PENDING):
            self.add_status(code)
            self.assertIsNone(self.run_command()['orders'][0]['skip_reason'])

    def test_escrow_or_terminal_history_is_preserved_even_if_current_status_is_confirmed(self):
        for code in (StatusType.ESCROWED, StatusType.PAID, StatusType.APPEALED,
                     StatusType.RELEASED, StatusType.REFUNDED):
            with self.subTest(code=code):
                self.add_status(code)
                self.add_status(StatusType.CONFIRMED)
                with self.assertRaisesMessage(CommandError, 'Ineligible order IDs'):
                    self.apply()
        self.assertFalse(Status.objects.filter(order=self.order, status=StatusType.CANCELED).exists())

    def test_any_recorded_transaction_or_valid_flag_prevents_cancellation(self):
        for txid, valid in (('unverified-transaction', False), (None, True)):
            with self.subTest(txid=txid, valid=valid):
                txn = Transaction.objects.create(
                    contract=self.contract, action='ESCROW', txid=txid, valid=valid,
                )
                with self.assertRaisesMessage(CommandError, 'Ineligible order IDs'):
                    self.apply()
                txn.delete()

    def test_batch_with_an_ineligible_order_cancels_nothing(self):
        other = Order.objects.create(
            owner=self.creator, ad_snapshot=self.snapshot, trade_amount=10000,
        )
        self.add_status(StatusType.ESCROWED, order=other)
        with self.assertRaises(CommandError):
            self.apply(order_id=[self.order.pk, other.pk])
        self.assertFalse(Status.objects.filter(status=StatusType.CANCELED).exists())
        self.notify.assert_not_called()

    def test_failure_during_cancellation_rolls_back_the_status(self):
        with patch(
            'rampp2p.management.commands.cancel_pending_p2p_orders.OrderMember.objects.filter',
            side_effect=RuntimeError('synthetic write failure'),
        ), self.assertRaises(RuntimeError):
            self.apply()
        self.assertFalse(Status.objects.filter(status=StatusType.CANCELED).exists())
        self.notify.assert_not_called()

    def test_repeated_apply_does_not_duplicate_cancellation(self):
        self.apply()
        result = self.apply()
        self.assertEqual(result['canceled_order_ids'], [])
        self.assertEqual(Status.objects.filter(order=self.order, status=StatusType.CANCELED).count(), 1)
