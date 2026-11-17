import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.urls import resolve
from rest_framework.test import APIRequestFactory, force_authenticate

from rampp2p.feature_control import require_p2p_feature
from rampp2p.models import FeatureControl, Order
from rampp2p.views.view_contract import ContractViewSet
from rampp2p.views.view_utils import check_feature_control


@override_settings(ROOT_URLCONF='rampp2p.urls')
class FeatureControlTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        FeatureControl.objects.bulk_create([
            FeatureControl(name=name, is_enabled=False)
            for name in FeatureControl.Type.values
        ])

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(wallet_hash='synthetic-wallet')
        permission = patch(
            'authentication.permissions.RampP2PIsAuthenticated.has_permission', return_value=True,
        )
        permission.start()
        self.addCleanup(permission.stop)

    def request(self, method, path, data=None, **headers):
        request = getattr(self.factory, method)(path, data=data or {}, format='json', **headers)
        force_authenticate(request, user=self.user)
        match = resolve(path.split('?')[0])
        return match.func(request, **match.kwargs)

    def assert_blocked(self, response, feature):
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response['Cache-Control'], 'no-store')
        data = json.loads(response.content)
        self.assertEqual(data['code'], 'p2p_feature_disabled')
        self.assertEqual(data['feature'], feature)

    def test_disabled_features_block_real_routes_before_business_queries(self):
        cases = (
            ('post', '/order/', {}, 'ORDER_CREATE'),
            ('post', '/order/', {'is_cash_in': True}, 'ORDER_CREATE'),
            ('post', '/order/contract/', {}, 'ORDER_ESCROW'),
            ('post', '/order/contract/', {'force': True, 'order_id': 1}, 'ORDER_ESCROW'),
            ('post', '/order/1/pending-escrow/', {}, 'ORDER_ESCROW'),
            ('post', '/ad/', {}, 'AD_CREATE'),
            ('put', '/ad/1/', {'is_public': True}, 'AD_UPDATE'),
            ('get', '/ad/share/?id=1', {}, 'AD_SHARE_LINKS'),
        )
        for method, path, data, feature in cases:
            with self.subTest(path=path, data=data):
                # Maintenance + action lookups; no business queries or writes.
                resolve(path.split('?')[0])
                with self.assertNumQueries(2):
                    response = self.request(method, path, data)
                self.assert_blocked(response, feature)

    def test_missing_feature_records_block_requests(self):
        FeatureControl.objects.all().delete()
        self.assert_blocked(self.request('post', '/order/'), 'ORDER_CREATE')
        self.assert_blocked(self.request('post', '/order/contract/'), 'ORDER_ESCROW')

    def test_missing_authentication_is_still_rejected_before_feature_lookup(self):
        match = resolve('/order/')
        request = self.factory.post('/order/', {}, format='json')
        with self.assertNumQueries(1):
            response = match.func(request, **match.kwargs)
        self.assertEqual(response.status_code, 401)

    def test_enabled_order_creation_reaches_normal_validation(self):
        FeatureControl.objects.filter(name='ORDER_CREATE').update(is_enabled=True)
        response = self.request('post', '/order/')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error'], 'trade_amount field is required')

    def test_toggle_changes_take_effect_on_the_next_request(self):
        self.assert_blocked(self.request('post', '/order/'), 'ORDER_CREATE')
        FeatureControl.objects.filter(name='ORDER_CREATE').update(is_enabled=True)
        self.assertEqual(self.request('post', '/order/').status_code, 400)
        FeatureControl.objects.filter(name='ORDER_CREATE').update(is_enabled=False)
        self.assert_blocked(self.request('post', '/order/'), 'ORDER_CREATE')

    def test_enabling_other_features_does_not_enable_orders(self):
        FeatureControl.objects.exclude(
            name__in=['ORDER_CREATE', 'P2P_MAINTENANCE'],
        ).update(is_enabled=True)
        self.assert_blocked(self.request('post', '/order/'), 'ORDER_CREATE')

    def test_legacy_contract_pending_escrow_handler_is_also_guarded(self):
        request = self.factory.post('/unused/', {}, format='json')
        force_authenticate(request, user=self.user)
        view = ContractViewSet.as_view({'post': 'pending_escrow'})
        with self.assertNumQueries(1):
            response = view(request, pk=1)
        self.assert_blocked(response, 'ORDER_ESCROW')

    def test_enabled_guard_preserves_handler_arguments_and_response(self):
        for feature in FeatureControl.Type.values:
            if feature == FeatureControl.Type.P2P_MAINTENANCE:
                continue
            with self.subTest(feature=feature):
                FeatureControl.objects.filter(name=feature).update(is_enabled=True)
                handler = Mock(return_value=object())
                view, request = object(), object()
                response = require_p2p_feature(feature)(handler)(view, request, pk=123)
                self.assertIs(response, handler.return_value)
                handler.assert_called_once_with(view, request, pk=123)

    def test_viewing_an_order_is_not_blocked_by_write_toggles(self):
        queryset = Mock()
        queryset.get.side_effect = Order.DoesNotExist
        with patch('rampp2p.views.view_order._optimize_order_queryset', return_value=queryset):
            with self.assertNumQueries(1):
                response = self.request('get', '/order/1/')
        self.assertEqual(response.status_code, 404)

    def test_cancellation_keeps_its_existing_authorization_check(self):
        order = SimpleNamespace(
            owner=SimpleNamespace(wallet_hash='another-user'),
            ad_snapshot=SimpleNamespace(ad=SimpleNamespace(owner=SimpleNamespace(wallet_hash='ad-owner'))),
        )
        with patch('rampp2p.views.view_order.models.Order.objects.get', return_value=order):
            with self.assertNumQueries(1):
                response = self.request('post', '/order/1/cancel/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Caller must be', response.data['error'])

    def test_settlement_verification_is_not_blocked_by_write_toggles(self):
        # Missing txid is still rejected by normal settlement validation,
        # rather than being blocked by ORDER_ESCROW (maintenance check only).
        for action in ('verify-release', 'verify-refund'):
            with self.subTest(action=action), self.assertNumQueries(1):
                response = self.request('post', '/order/1/' + action + '/')
                self.assertEqual(response.status_code, 400)
                self.assertIn('txid', response.data['error'])

    def test_feature_control_endpoint_remains_available(self):
        response = check_feature_control(self.factory.get('/feature-control/'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(json.loads(response.content)['ORDER_ESCROW'])
