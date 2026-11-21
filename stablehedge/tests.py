from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from stablehedge.views import TestUtilsViewSet


class PriceMessageSecretTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = TestUtilsViewSet.as_view({'post': 'price_message'})

    def test_wif_is_read_only_from_the_post_body(self):
        request = self.factory.post(
            '/api/stablehedge/test-utils/price_message/',
            {'wif': 'synthetic-private-key', 'price': 1234},
            format='json',
        )
        with patch(
            'stablehedge.views.ScriptFunctions.generatePriceMessage',
            return_value={'priceData': {}, 'publicKey': 'synthetic'},
        ) as generate:
            response = self.view(request)

        self.assertEqual(response.status_code, 200)
        generate.assert_called_once()
        self.assertEqual(generate.call_args.args[0]['wif'], 'synthetic-private-key')
        self.assertNotIn('privateKey', response.data)

    def test_wif_is_not_accepted_from_the_query_string(self):
        request = self.factory.get(
            '/api/stablehedge/test-utils/price_message/',
            {'wif': 'synthetic-private-key'},
        )
        with patch(
            'stablehedge.views.ScriptFunctions.generatePriceMessage'
        ) as generate:
            response = self.view(request)

        self.assertEqual(response.status_code, 405)
        generate.assert_not_called()
