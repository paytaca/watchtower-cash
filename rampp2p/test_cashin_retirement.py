from unittest.mock import Mock, patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from rampp2p.models import Ad, AdSnapshot, CryptoCurrency, FeatureControl, FiatCurrency, Order, Peer, Status
from rampp2p.views.view_order import OrderViewSet


class CashinRetirementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.buyer = Peer.objects.create(
            name='synthetic-buyer', wallet_hash='synthetic-buyer',
            public_key='synthetic-key', address='synthetic-address',
        )
        cls.seller = Peer.objects.create(
            name='synthetic-seller', wallet_hash='synthetic-seller',
            public_key='synthetic-key', address='synthetic-address',
        )
        fiat = FiatCurrency.objects.create(name='Synthetic fiat', symbol='TST')
        crypto = CryptoCurrency.objects.create(name='Synthetic BCH', symbol='TESTBCH')
        with patch('rampp2p.signals.AdSummaryMessage.send_safe'):
            cls.ad = Ad.objects.create(
                owner=cls.seller, trade_type='SELL', price_type='FIXED',
                fiat_currency=fiat, crypto_currency=crypto,
            )
        cls.snapshot = AdSnapshot.objects.create(
            ad=cls.ad, trade_type='SELL', price_type='FIXED',
            fiat_currency=fiat, crypto_currency=crypto, appeal_cooldown_choice=60,
        )
        cls.historical_order = Order.objects.create(
            owner=cls.buyer, ad_snapshot=cls.snapshot, is_cash_in=True,
        )
        Status.objects.bulk_create([Status(order=cls.historical_order, status='ESCRW')])
        FeatureControl.objects.create(name=FeatureControl.Type.ORDER_CREATE, is_enabled=True)

    def setUp(self):
        self.factory = APIRequestFactory()
        patcher = patch('authentication.permissions.RampP2PIsAuthenticated.has_permission', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.effects = {}
        for method in (
            'check_create_permissions', 'set_expiration_date', 'submit_order',
            'create_members', 'mark_creator_as_read', 'update_ad_trade_amount', 'confirm_order',
        ):
            patcher = patch.object(OrderViewSet, method, return_value={})
            self.effects[method] = patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(OrderViewSet, 'snapshot_ad', return_value=self.snapshot)
        self.snapshot_mock = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(OrderViewSet, 'generate_tracking_id', return_value='synthetic-new-order')
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch('rampp2p.views.view_order.serializers.OrderSerializer', return_value=Mock(data={'synthetic': True}))
        patcher.start()
        self.addCleanup(patcher.stop)

    def create_order(self, flag, format='json'):
        data = {'ad': self.ad.pk, 'trade_amount': 10000}
        if flag != 'omit':
            data['is_cash_in'] = flag
        request = self.factory.post('/order/', data, format=format)
        force_authenticate(request, user=self.buyer)
        return OrderViewSet.as_view({'post': 'create'})(request)

    def test_cash_in_requests_are_rejected_before_any_order_side_effects(self):
        before = Order.objects.count()
        for flag in (True, 'true', 'True', '1', 1, 'yes', 'on'):
            with self.subTest(flag=flag):
                response = self.create_order(flag)
                self.assertEqual(response.status_code, 400)
                self.assertIn('retired', str(response.data))
        self.assertEqual(Order.objects.count(), before)
        self.snapshot_mock.assert_not_called()
        for effect in self.effects.values():
            effect.assert_not_called()
        self.assertTrue(Order.objects.get(pk=self.historical_order.pk).is_cash_in)
        self.assertEqual(Status.objects.get(order=self.historical_order).status, 'ESCRW')

    def test_invalid_flags_cannot_bypass_retirement(self):
        for flag in (None, [], {}, 'invalid'):
            with self.subTest(flag=flag):
                self.assertEqual(self.create_order(flag).status_code, 400)
        self.snapshot_mock.assert_not_called()
        self.assertEqual(Order.objects.count(), 1)

    def test_regular_order_creation_still_accepts_omitted_and_false_flags(self):
        for flag in ('omit', False, 'false', '0', 0):
            with self.subTest(flag=flag):
                response = self.create_order(flag)
                self.assertEqual(response.status_code, 201)
                created = Order.objects.exclude(pk=self.historical_order.pk).get()
                self.assertFalse(created.is_cash_in)
                created.delete()
        self.assertTrue(Order.objects.get(pk=self.historical_order.pk).is_cash_in)

    def test_form_flags_use_the_same_retirement_policy(self):
        self.assertEqual(self.create_order('true', format='multipart').status_code, 400)
        self.snapshot_mock.assert_not_called()
        self.assertEqual(self.create_order('false', format='multipart').status_code, 201)
        self.assertFalse(Order.objects.exclude(pk=self.historical_order.pk).get().is_cash_in)
