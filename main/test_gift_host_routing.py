from types import ModuleType

from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, override_settings
from django.urls import Resolver404, path, re_path, resolve

from watchtower.gift_host import GiftHostMiddleware


@override_settings(ALLOWED_HOSTS=['*'], USE_X_FORWARDED_HOST=False)
class GiftHostRoutingTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = GiftHostMiddleware(lambda request: request)
        self.root = ModuleType('synthetic_primary_routes')
        self.root.urlpatterns = [
            path('admin/', lambda request: HttpResponse('primary-admin')),
            path('api/ramp-p2p/', lambda request: HttpResponse('primary-p2p')),
            re_path(r'api/multisig/', lambda request: HttpResponse('primary-multisig')),
        ]

    def gift_request(self, path='/api/ramp-p2p/', host='gifts.paytaca.com'):
        return self.middleware(self.factory.get(path, HTTP_HOST=host))

    def test_gift_host_case_port_and_trailing_dot_select_restricted_routes(self):
        for host in ('gifts.paytaca.com', 'GIFTS.PAYTACA.COM',
                     'gifts.paytaca.com:443', 'gifts.paytaca.com.:443'):
            with self.subTest(host=host):
                self.assertEqual(self.gift_request(host=host).urlconf, 'paytacagifts.public_urls')

    def test_primary_and_ssh_tunnel_hosts_keep_existing_routing(self):
        for host in ('watchtower.cash', '127.0.0.1:8088', 'localhost:8088'):
            with self.subTest(host=host):
                self.assertFalse(hasattr(self.gift_request(host=host), 'urlconf'))

    def test_forwarded_host_cannot_replace_the_host_used_for_routing(self):
        request = self.factory.get('/admin/', HTTP_HOST='gifts.paytaca.com',
                                   HTTP_X_FORWARDED_HOST='watchtower.cash')
        self.assertEqual(self.middleware(request).urlconf, 'paytacagifts.public_urls')

    def test_all_existing_gift_api_routes_resolve(self):
        routes = (
            ('/api/campaigns/synthetic-wallet/list/', 'campaign-list'),
            ('/api/gifts/synthetic-wallet/list/', 'gift-list'),
            ('/api/gifts/synthetic-wallet/create/', 'gift-create'),
            ('/api/gifts/synthetic-code/claim', 'gift-claim'),
            ('/api/gifts/synthetic-code/claim/', 'gift-claim-slash'),
            ('/api/gifts/synthetic-code/recover', 'gift-recover'),
            ('/api/gifts/synthetic-code/', 'gift-retrieve'),
            ('/api/claim/', 'claim'),
        )
        for url, name in routes:
            with self.subTest(url=url):
                request = self.gift_request(url)
                self.assertEqual(resolve(url, urlconf=request.urlconf).url_name, name)

    def test_claim_pages_and_platform_association_files_resolve(self):
        for url in ('/claim', '/claim/', '/.well-known/apple-app-site-association',
                    '/.well-known/assetlinks.json'):
            with self.subTest(url=url):
                request = self.gift_request(url)
                self.assertTrue(callable(resolve(url, urlconf=request.urlconf).func))

    def test_other_services_cannot_resolve_through_gift_hostname(self):
        urls = ('/admin/', '/admin/login/', '/api/ramp-p2p/', '/api/paytacapos/',
                '/api/payment-requests/pay/', '/api/subscription/', '/api/auth/',
                '/api/stablehedge/', '/api/multisig/', '/api/docs/',
                '/ws/ramp-p2p/subscribe/order/1/', '/claim/api/ramp-p2p/',
                '/api/gifts/synthetic/api/multisig/', '/.well-known/admin/')
        for url in urls:
            with self.subTest(url=url), self.assertRaises(Resolver404):
                resolve(url, urlconf=self.gift_request(url).urlconf)

    def test_full_requests_do_not_fall_back_to_primary_urlconf(self):
        with override_settings(ROOT_URLCONF=self.root, MIDDLEWARE=[
            'watchtower.gift_host.GiftHostMiddleware',
        ]):
            client = Client()
            for url in ('/admin/', '/api/ramp-p2p/', '/api/multisig/',
                        '/api/gifts/synthetic/api/multisig/'):
                for method in ('get', 'post'):
                    with self.subTest(url=url, method=method):
                        response = getattr(client, method)(url, HTTP_HOST='gifts.paytaca.com')
                        self.assertEqual(response.status_code, 404)
            self.assertEqual(client.get('/admin/', HTTP_HOST='watchtower.cash').content, b'primary-admin')

    def test_slash_redirects_only_consider_gift_routes(self):
        with override_settings(ROOT_URLCONF=self.root, APPEND_SLASH=True, MIDDLEWARE=[
            'watchtower.gift_host.GiftHostMiddleware',
            'django.middleware.common.CommonMiddleware',
        ]):
            client = Client()
            response = client.get('/api/gifts/synthetic-wallet/list', HTTP_HOST='gifts.paytaca.com')
            self.assertEqual(response.status_code, 301)
            self.assertEqual(response['Location'], '/api/gifts/synthetic-wallet/list/')
            self.assertEqual(client.get('/admin', HTTP_HOST='gifts.paytaca.com').status_code, 404)
