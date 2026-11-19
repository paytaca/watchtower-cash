from django.test import SimpleTestCase, override_settings
from django.urls import NoReverseMatch, Resolver404, resolve, reverse


@override_settings(ROOT_URLCONF='rampp2p.urls')
class RetiredCashinRouteTests(SimpleTestCase):
    def test_retired_cash_in_routes_do_not_resolve(self):
        for path in (
            '/cash-in/order/', '/cash-in/order/alerts/',
            '/order/cash-in/', '/order/cash-in/alerts/',
            '/ad/cash-in/', '/cash-in/ad/', '/cash-in/ad/payment-types/',
            '/cash-in/presets/',
        ):
            with self.subTest(path=path), self.assertRaises(Resolver404):
                resolve(path)

    def test_retired_route_names_cannot_be_reversed(self):
        for name in ('cashin-order-list', 'cashin-order-alerts'):
            with self.subTest(name=name), self.assertRaises(NoReverseMatch):
                reverse(name)

    def test_standard_order_and_ad_routes_remain_available(self):
        for path in (
            '/order/', '/order/123/', '/order/123/status/',
            '/ad/', '/ad/123/', '/ad/currency/',
        ):
            with self.subTest(path=path):
                self.assertIsNotNone(resolve(path))
