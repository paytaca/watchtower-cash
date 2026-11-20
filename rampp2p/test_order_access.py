from datetime import timedelta
from unittest.mock import Mock, patch

from django.db.models.signals import post_save
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from rampp2p.models import (
    Ad, AdSnapshot, Arbiter, Contract, CryptoCurrency, FiatCurrency,
    Order, OrderMember, Peer, Status,
)
from rampp2p.signals import on_order_update
from rampp2p.views.view_ad import AdSnapshotViewSet
from rampp2p.views.view_contract import ContractViewSet
from rampp2p.views.view_order import OrderStatusViewSet, OrderViewSet


class OrderAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        def peer(pk, name):
            return Peer.objects.create(
                pk=pk, name=name, wallet_hash='synthetic-' + name,
                public_key='synthetic-key', address='synthetic-address', chat_identity_id=pk,
            )

        cls.buyer = peer(1, 'buyer')
        cls.seller = peer(2, 'seller')
        cls.outsider = peer(3, 'outsider')
        cls.other_peer = peer(4, 'other-peer')
        # Independent model IDs overlap deliberately.
        cls.arbiter = Arbiter.objects.create(
            pk=3, name='assigned', wallet_hash='synthetic-assigned', chat_identity_id=30,
            public_key='synthetic-key', address='synthetic-address', is_disabled=False,
        )
        cls.other_arbiter = Arbiter.objects.create(
            pk=1, name='unassigned', wallet_hash='synthetic-unassigned', chat_identity_id=40,
            public_key='synthetic-key', address='synthetic-address', is_disabled=False,
        )
        fiat = FiatCurrency.objects.create(name='Synthetic fiat', symbol='TST')
        crypto = CryptoCurrency.objects.create(name='Synthetic BCH', symbol='TESTBCH')

        def order(ad_owner, creator, trade_type):
            with patch('rampp2p.signals.AdSummaryMessage.send_safe'):
                ad = Ad.objects.create(
                    owner=ad_owner, trade_type=trade_type, price_type='FIXED',
                    fiat_currency=fiat, crypto_currency=crypto,
                )
            snapshot = AdSnapshot.objects.create(
                ad=ad, trade_type=trade_type, price_type='FIXED', fiat_currency=fiat,
                crypto_currency=crypto, appeal_cooldown_choice=60,
            )
            result = Order.objects.create(
                owner=creator, ad_snapshot=snapshot, arbiter=cls.arbiter,
                chat_session_ref='original-chat', trade_amount=10000,
                expires_at=timezone.now() + timedelta(hours=1),
            )
            Status.objects.bulk_create([Status(order=result, status='SBM')])
            buyer, seller = (creator, ad_owner) if trade_type == 'SELL' else (ad_owner, creator)
            OrderMember.objects.bulk_create([
                OrderMember(order=result, peer=buyer, type='BUYER'),
                OrderMember(order=result, peer=seller, type='SELLER'),
                OrderMember(order=result, arbiter=cls.arbiter, type='ARBITER'),
            ])
            return result

        cls.order = order(cls.seller, cls.buyer, 'SELL')
        cls.buy_order = order(cls.buyer, cls.seller, 'BUY')
        cls.foreign_order = order(cls.outsider, cls.other_peer, 'SELL')
        cls.contract = Contract.objects.create(
            order=cls.order, address='synthetic-contract-address',
            arbitration_fee=200, service_fee=300, contract_fee=100,
        )

    def setUp(self):
        self.factory = APIRequestFactory()
        self.mocks = {}
        patches = {
            'permission': ('authentication.permissions.RampP2PIsAuthenticated.has_permission', True),
            'optimize': ('rampp2p.views.view_order._optimize_order_queryset', None),
            'ratings': ('rampp2p.views.view_order._peer_ratings_for_orders', {}),
            'order_serializer': ('rampp2p.views.view_order.serializers.OrderSerializer', None),
            'contract_serializer': ('rampp2p.views.view_contract.serializers.ContractSerializer', None),
            'snapshot_serializer': ('rampp2p.views.view_ad.serializers.AdSnapshotSerializer', None),
            'ongoing': ('rampp2p.views.view_order.utils._count_ongoing', 0),
            'cashin_alerts': ('rampp2p.views.view_order.utils.check_has_cashin_alerts', False),
            'push': ('rampp2p.views.view_order.send_push_notification', None),
            'websocket': ('rampp2p.views.view_order.websocket.send_order_update', None),
            'cashin_websocket': ('rampp2p.views.view_order.websocket.send_cashin_order_alert', None),
            'general_websocket': ('rampp2p.views.view_order.websocket.send_general_update', None),
            'fees': ('rampp2p.views.view_contract.get_trading_fees', (100, {'contract_fee': 100})),
        }
        for name, (target, value) in patches.items():
            mocked = patch(target, return_value=value)
            self.mocks[name] = mocked.start()
            self.addCleanup(mocked.stop)
        self.mocks['optimize'].side_effect = lambda queryset: queryset
        def serialize_order(order, many=False, **kwargs):
            if many:
                return Mock(data=[{'id': item.pk} for item in order])
            return Mock(data={
                'id': order.pk, 'status': {'value': 'SBM'}, 'chat_session_ref': order.chat_session_ref,
            })

        self.mocks['order_serializer'].side_effect = serialize_order
        self.mocks['contract_serializer'].return_value = Mock(data={'address': 'synthetic-contract-address'})
        self.mocks['snapshot_serializer'].return_value = Mock(data={'snapshot': 'synthetic'})
        # Real status serialization and ORM writes, without external signal delivery.
        if post_save.disconnect(on_order_update, sender=Status):
            self.addCleanup(post_save.connect, on_order_update, sender=Status)

    def request(self, view, action, user, method='get', pk=None, data=None, **headers):
        headers.setdefault('HTTP_WALLET_HASH', user.wallet_hash)
        request = getattr(self.factory, method)('/unused/', data or {}, format='json', **headers)
        force_authenticate(request, user=user)
        kwargs = {} if pk is None else {'pk': pk}
        return view.as_view({method: action})(request, **kwargs)

    def private_reads(self):
        return (
            (OrderViewSet, 'retrieve', self.order.pk),
            (OrderViewSet, 'members', self.order.pk),
            (OrderStatusViewSet, 'list_status', self.order.pk),
            (AdSnapshotViewSet, 'retrieve', self.order.ad_snapshot_id),
            (AdSnapshotViewSet, 'retrieve_by_order', self.order.pk),
            (ContractViewSet, 'retrieve', self.contract.pk),
            (ContractViewSet, 'retrieve_by_order', self.order.pk),
            (ContractViewSet, 'transactions', self.contract.pk),
            (ContractViewSet, 'transactions_by_order', self.order.pk),
            (ContractViewSet, 'contract_fees', self.order.pk),
        )

    def test_unrelated_peers_and_arbiters_cannot_read_private_order_data(self):
        for actor in (self.outsider, self.other_arbiter):
            for view, action, pk in self.private_reads():
                with self.subTest(actor=actor.name, view=view.__name__, action=action):
                    response = self.request(view, action, actor, pk=pk)
                    self.assertEqual(response.status_code, 403)
        self.mocks['order_serializer'].assert_not_called()
        self.mocks['contract_serializer'].assert_not_called()
        self.mocks['snapshot_serializer'].assert_not_called()

    def test_buyer_seller_and_assigned_arbiter_keep_private_read_access(self):
        for actor in (self.buyer, self.seller, self.arbiter):
            for view, action, pk in self.private_reads():
                with self.subTest(actor=actor.name, view=view.__name__, action=action):
                    self.assertEqual(self.request(view, action, actor, pk=pk).status_code, 200)

    def test_header_identity_cannot_override_the_authenticated_actor(self):
        response = self.request(
            OrderViewSet, 'retrieve', self.outsider, pk=self.order.pk,
            HTTP_WALLET_HASH=self.buyer.wallet_hash,
        )
        self.assertEqual(response.status_code, 403)
        self.mocks['order_serializer'].assert_not_called()

    def test_order_serialization_uses_authenticated_identity(self):
        response = self.request(
            OrderViewSet, 'retrieve', self.buyer, pk=self.order.pk,
            HTTP_WALLET_HASH=self.outsider.wallet_hash,
        )
        self.assertEqual(response.status_code, 200)
        context = self.mocks['order_serializer'].call_args[1]['context']
        self.assertEqual(context['wallet_hash'], self.buyer.wallet_hash)

    def test_private_order_list_keeps_peer_account_scope(self):
        for actor, expected in ((self.buyer, self.order.pk), (self.seller, self.buy_order.pk)):
            with self.subTest(actor=actor.name):
                response = self.request(
                    OrderViewSet, 'list', actor,
                    data={'status_type': 'ONGOING', 'owned': 'true', 'limit': 100},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row['id'] for row in response.data['orders']], [expected])

    def test_arbiter_wallet_collision_cannot_expose_peer_order_lists(self):
        Arbiter.objects.filter(pk=self.other_arbiter.pk).update(wallet_hash=self.buyer.wallet_hash)
        actor = Arbiter.objects.get(pk=self.other_arbiter.pk)
        response = self.request(
            OrderViewSet, 'list', actor,
            data={'status_type': 'ONGOING', 'owned': 'true', 'limit': 100},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['orders'], [])

    def test_removed_arbiter_assignment_revokes_private_reads(self):
        Order.objects.filter(pk=self.order.pk).update(arbiter=None)
        for view, action, pk in self.private_reads():
            with self.subTest(view=view.__name__, action=action):
                self.assertEqual(self.request(view, action, self.arbiter, pk=pk).status_code, 403)

    def test_unrelated_actor_cannot_change_chat_reference_or_fetch_order_via_patch(self):
        for actor in (self.outsider, self.other_arbiter):
            for data in ({}, {'chat_session_ref': 'attacker-chat'}):
                with self.subTest(actor=actor.name, data=data):
                    response = self.request(
                        OrderViewSet, 'partial_update', actor, method='patch',
                        pk=self.order.pk, data=data,
                    )
                    self.assertEqual(response.status_code, 403)
        self.assertEqual(Order.objects.get(pk=self.order.pk).chat_session_ref, 'original-chat')
        self.mocks['order_serializer'].assert_not_called()

    def test_actual_participants_can_update_chat_reference(self):
        for actor in (self.buyer, self.seller, self.arbiter):
            with self.subTest(actor=actor.name):
                reference = 'chat-' + actor.name
                response = self.request(
                    OrderViewSet, 'partial_update', actor, method='patch',
                    pk=self.order.pk, data={'chat_session_ref': reference},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(Order.objects.get(pk=self.order.pk).chat_session_ref, reference)

    def test_unrelated_actor_cannot_mark_order_members_read(self):
        for actor in (self.outsider, self.other_arbiter):
            response = self.request(OrderViewSet, 'members', actor, method='patch', pk=self.order.pk)
            self.assertEqual(response.status_code, 403)
        self.assertFalse(OrderMember.objects.filter(order=self.order, read_at__isnull=False).exists())
        self.mocks['general_websocket'].assert_not_called()

    def test_member_read_acknowledgment_changes_only_the_authenticated_member(self):
        for actor in (self.buyer, self.seller, self.arbiter):
            with self.subTest(actor=actor.name):
                OrderMember.objects.filter(order=self.order).update(read_at=None)
                response = self.request(OrderViewSet, 'members', actor, method='patch', pk=self.order.pk)
                self.assertEqual(response.status_code, 200)
                changed = OrderMember.objects.filter(order=self.order, read_at__isnull=False).get()
                if isinstance(actor, Peer):
                    self.assertEqual(changed.peer_id, actor.pk)
                    self.assertIsNone(changed.arbiter_id)
                else:
                    self.assertEqual(changed.arbiter_id, actor.pk)
                    self.assertIsNone(changed.peer_id)

    def test_only_ad_owner_can_confirm_sell_and_buy_ads(self):
        for order, ad_owner, creator in (
            (self.order, self.seller, self.buyer), (self.buy_order, self.buyer, self.seller),
        ):
            for actor in (creator, self.outsider, self.arbiter, self.other_arbiter):
                with self.subTest(order=order.pk, actor=actor.name):
                    response = self.request(OrderStatusViewSet, 'confirm', actor, method='post', pk=order.pk)
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(Status.objects.filter(order=order).count(), 1)
            self.mocks['push'].assert_not_called()
            response = self.request(
                OrderStatusViewSet, 'confirm', ad_owner, method='post', pk=order.pk,
                data={'created_by': self.outsider.wallet_hash},
            )
            self.assertEqual(response.status_code, 200)
            confirmed = Status.objects.get(order=order, status='CNF')
            self.assertEqual(confirmed.created_by, ad_owner.wallet_hash)
            self.mocks['push'].reset_mock()

    def test_expired_canceled_and_already_confirmed_orders_cannot_be_confirmed(self):
        Order.objects.filter(pk=self.order.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.request(OrderStatusViewSet, 'confirm', self.seller, method='post', pk=self.order.pk)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Status.objects.filter(order=self.order).count(), 1)
        for code in ('CNCL', 'CNF'):
            with self.subTest(code=code):
                Status.objects.bulk_create([Status(order=self.order, status=code)])
                before = Status.objects.filter(order=self.order).count()
                response = self.request(OrderStatusViewSet, 'confirm', self.seller, method='post', pk=self.order.pk)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(Status.objects.filter(order=self.order).count(), before)
        self.mocks['push'].assert_not_called()

    def test_mixed_bulk_read_request_cannot_write_any_statuses(self):
        for actor in (self.buyer, self.seller):
            with self.subTest(actor=actor.name):
                response = self.request(
                    OrderStatusViewSet, 'read_order_status', actor, method='patch',
                    data={'order_ids': [self.order.pk, self.foreign_order.pk]},
                )
                self.assertEqual(response.status_code, 403)
                self.assertFalse(Status.objects.filter(buyer_read_at__isnull=False).exists())
                self.assertFalse(Status.objects.filter(seller_read_at__isnull=False).exists())
        self.mocks['general_websocket'].assert_not_called()

    def test_only_trading_peers_can_bulk_mark_buy_and_sell_orders_read(self):
        for actor in (self.outsider, self.arbiter, self.other_arbiter):
            with self.subTest(actor=actor.name):
                response = self.request(
                    OrderStatusViewSet, 'read_order_status', actor, method='patch',
                    data={'order_ids': [self.order.pk, self.buy_order.pk]},
                )
                self.assertEqual(response.status_code, 403)
        for actor, own_column, other_column in (
            (self.buyer, 'buyer_read_at', 'seller_read_at'),
            (self.seller, 'seller_read_at', 'buyer_read_at'),
        ):
            with self.subTest(actor=actor.name):
                Status.objects.all().update(buyer_read_at=None, seller_read_at=None)
                response = self.request(
                    OrderStatusViewSet, 'read_order_status', actor, method='patch',
                    data={'order_ids': [self.order.pk, self.buy_order.pk]},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(Status.objects.filter(**{own_column + '__isnull': False}).count(), 2)
                self.assertFalse(Status.objects.filter(**{other_column + '__isnull': False}).exists())
                untouched = Status.objects.get(order=self.foreign_order)
                self.assertIsNone(untouched.buyer_read_at)
                self.assertIsNone(untouched.seller_read_at)

    def test_bulk_read_resolves_each_order_role_in_a_mixed_role_batch(self):
        original = self.order.ad_snapshot
        with patch('rampp2p.signals.AdSummaryMessage.send_safe'):
            ad = Ad.objects.create(
                owner=self.buyer, trade_type='SELL', price_type='FIXED',
                fiat_currency=original.fiat_currency, crypto_currency=original.crypto_currency,
            )
        snapshot = AdSnapshot.objects.create(
            ad=ad, trade_type='SELL', price_type='FIXED',
            fiat_currency=original.fiat_currency, crypto_currency=original.crypto_currency,
            appeal_cooldown_choice=60,
        )
        reverse_order = Order.objects.create(
            owner=self.seller, ad_snapshot=snapshot, trade_amount=10000,
        )
        Status.objects.bulk_create([Status(order=reverse_order, status='SBM')])
        response = self.request(
            OrderStatusViewSet, 'read_order_status', self.buyer, method='patch',
            data={'order_ids': [self.order.pk, reverse_order.pk]},
        )
        self.assertEqual(response.status_code, 200)
        buying = Status.objects.get(order=self.order)
        selling = Status.objects.get(order=reverse_order)
        self.assertIsNotNone(buying.buyer_read_at)
        self.assertIsNone(buying.seller_read_at)
        self.assertIsNotNone(selling.seller_read_at)
        self.assertIsNone(selling.buyer_read_at)

    def test_bulk_read_preserves_existing_acknowledgments_for_both_roles(self):
        earlier = timezone.now() - timedelta(hours=1)
        Status.objects.filter(order=self.order).update(buyer_read_at=earlier, seller_read_at=earlier)
        for actor in (self.buyer, self.seller):
            response = self.request(
                OrderStatusViewSet, 'read_order_status', actor, method='patch',
                data={'order_ids': [self.order.pk, self.buy_order.pk]},
            )
            self.assertEqual(response.status_code, 200)
            stored = Status.objects.get(order=self.order)
            self.assertEqual(stored.buyer_read_at, earlier)
            self.assertEqual(stored.seller_read_at, earlier)

    def test_unknown_or_invalid_bulk_order_ids_do_not_change_records(self):
        for ids, expected in (([self.order.pk, 999999], 403), ('not-a-list', 400), ([None], 400)):
            with self.subTest(ids=ids):
                response = self.request(
                    OrderStatusViewSet, 'read_order_status', self.buyer,
                    method='patch', data={'order_ids': ids},
                )
                self.assertEqual(response.status_code, expected)
        self.assertFalse(Status.objects.filter(buyer_read_at__isnull=False).exists())

    def test_single_status_read_is_limited_to_the_correct_peer_role(self):
        for actor, column in ((self.buyer, 'buyer_read_at'), (self.seller, 'seller_read_at')):
            response = self.request(OrderStatusViewSet, 'read_status', actor, method='patch', pk=self.order.pk)
            self.assertEqual(response.status_code, 200)
            self.assertIsNotNone(getattr(Status.objects.get(order=self.order), column))
        for actor in (self.outsider, self.other_arbiter):
            response = self.request(OrderStatusViewSet, 'read_status', actor, method='patch', pk=self.order.pk)
            self.assertEqual(response.status_code, 403)

    def test_canceled_contract_state_is_only_disclosed_to_participants(self):
        Status.objects.bulk_create([Status(order=self.order, status='CNCL')])
        response = self.request(ContractViewSet, 'retrieve', self.outsider, pk=self.contract.pk)
        self.assertEqual(response.status_code, 403)
        response = self.request(ContractViewSet, 'retrieve', self.buyer, pk=self.contract.pk)
        self.assertEqual(response.status_code, 410)
