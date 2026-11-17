import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import resolve, URLPattern
from rest_framework.test import APIRequestFactory

from rampp2p.models import FeatureControl
from rampp2p.urls import urlpatterns
from rampp2p.views.view_utils import check_feature_control


@override_settings(ROOT_URLCONF='rampp2p.urls')
class P2PMaintenanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.control = FeatureControl.objects.create(
            name='P2P_MAINTENANCE', is_enabled=True,
        )

    def setUp(self):
        self.factory = APIRequestFactory()

    def request(self, method, path, data=None):
        request = getattr(self.factory, method)(path, data=data or {}, format='json')
        match = resolve(path)
        return match.func(request, **match.kwargs)

    def assert_maintenance(self, response):
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(json.loads(response.content)['code'], 'p2p_maintenance')

    def test_order_and_contract_reads_are_blocked_before_authentication(self):
        paths = (
            '/order/', '/order/123/', '/order/123/members/', '/order/123/status/',
            '/order/123/contract/', '/order/123/contract/fees/',
            '/order/123/contract/transactions/', '/order/contract/123/',
            '/order/contract/123/transactions/', '/ad/snapshot/123/',
        )
        for path in paths:
            with self.subTest(path=path), self.assertNumQueries(1):
                self.assert_maintenance(self.request('get', path))

    def test_writes_and_recovery_routes_are_blocked_in_full_maintenance(self):
        cases = (
            ('post', '/order/'), ('post', '/order/contract/'),
            ('post', '/order/123/pending-escrow/'), ('patch', '/peer/'),
            ('patch', '/arbiter/'), ('post', '/order/123/cancel/'),
            ('post', '/order/123/verify-escrow/'),
            ('post', '/order/123/verify-release/'), ('post', '/order/123/verify-refund/'),
            ('post', '/appeal/'), ('post', '/chats/webhook/'),
        )
        for method, path in cases:
            with self.subTest(method=method, path=path), self.assertNumQueries(1):
                self.assert_maintenance(self.request(method, path))

    def test_public_and_cash_in_aliases_are_blocked(self):
        for path in (
            '/order/public/', '/order/public/123/', '/order/public.json',
            '/appeal/public/', '/cash-in/order/', '/order/cash-in/',
            '/cash-in/order/alerts/', '/order/cash-in/alerts/', '/ad/share/',
        ):
            with self.subTest(path=path), self.assertNumQueries(1):
                self.assert_maintenance(self.request('get', path))

    def test_every_routed_view_except_feature_reads_has_the_guard(self):
        # Invoke every callback with a sentinel request. A guarded callback must
        # return maintenance without accessing request properties or view data.
        for route in urlpatterns:
            with self.subTest(route=str(route.pattern)):
                self.assertIsInstance(route, URLPattern)
                if route.callback is check_feature_control:
                    continue
                with self.assertNumQueries(1):
                    self.assert_maintenance(route.callback(object()))

    def test_feature_control_aliases_remain_available(self):
        for path in ('/feature-control/', '/feature-toggles/'):
            with self.subTest(path=path):
                response = self.request('get', path)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(json.loads(response.content)['P2P_MAINTENANCE'])

    def test_turning_maintenance_off_restores_normal_authentication(self):
        self.assert_maintenance(self.request('get', '/order/123/'))
        FeatureControl.objects.filter(pk=self.control.pk).update(is_enabled=False)
        self.assertEqual(self.request('get', '/order/123/').status_code, 401)

    def test_missing_maintenance_record_does_not_enable_full_pause(self):
        FeatureControl.objects.filter(pk=self.control.pk).delete()
        self.assertEqual(self.request('get', '/order/123/').status_code, 401)

    def test_full_pause_overrides_individually_enabled_features(self):
        FeatureControl.objects.bulk_create([
            FeatureControl(name=name, is_enabled=True)
            for name in FeatureControl.Type.values if name != 'P2P_MAINTENANCE'
        ])
        with self.assertNumQueries(1):
            self.assert_maintenance(self.request('post', '/order/'))

    def test_view_and_task_code_cannot_run_during_maintenance(self):
        with patch('rampp2p.views.view_contract.ContractViewSet.dispatch') as dispatch, \
             patch('rampp2p.views.view_contract.create_contract') as generate:
            self.assert_maintenance(self.request('post', '/order/contract/', {'force': True}))
        dispatch.assert_not_called()
        generate.assert_not_called()
