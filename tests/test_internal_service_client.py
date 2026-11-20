"""Exercise the production transport and both Python runners using synthetic config."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from django.core.exceptions import ImproperlyConfigured

ROOT = Path(__file__).resolve().parents[1]


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Isolate decouple from local .env files, including on minimal test installations.
config_stub = types.ModuleType('decouple')
config_stub.config = lambda name, default='': default
with patch.dict(sys.modules, {'decouple': config_stub}):
    client = load_file('internal_client_under_test', 'internal_services/client.py')

TOKEN = 'synthetic-service-token-abcdefghijklmnopqrstuvwxyz-0123456789'


class InternalServiceClientTests(unittest.TestCase):
    def test_missing_or_invalid_configuration_sends_no_requests(self):
        for token in ['', 'short', 'x' * 64, 'space ' * 12]:
            with patch.object(client, 'config', return_value=token), patch.object(client.requests, 'Session') as session:
                with self.assertRaises(ImproperlyConfigured):
                    client.post_script_request('stablehedge', {})
                session.assert_not_called()

    def test_tokens_are_service_specific_and_never_sent_through_proxies_or_redirects(self):
        for service, variable, port in [
            ('stablehedge', 'STABLEHEDGE_JS_AUTH_TOKEN', 3010),
            ('anyhedge', 'ANYHEDGE_JS_AUTH_TOKEN', 3020),
        ]:
            with self.subTest(service=service), patch.object(client, 'config', return_value=TOKEN) as config, patch.object(client.requests, 'Session') as factory:
                session = factory.return_value.__enter__.return_value
                result = client.post_script_request(service, {'function': 'test', 'params': []})
                config.assert_called_once_with(variable, default='')
                self.assertFalse(session.trust_env)
                session.post.assert_called_once_with(
                    'http://127.0.0.1:{}/'.format(port),
                    json={'function': 'test', 'params': []},
                    headers={'Authorization': 'Bearer ' + TOKEN},
                    timeout=30, allow_redirects=False,
                )
                self.assertIs(result, session.post.return_value)

    def test_unknown_service_cannot_select_an_arbitrary_token_destination(self):
        with patch.object(client.requests, 'Session') as session:
            with self.assertRaises(KeyError):
                client.post_script_request('http://untrusted.example/', {})
            session.assert_not_called()

    def test_both_runners_use_authenticated_transport_and_preserve_success(self):
        for app in ['stablehedge', 'anyhedge']:
            with patch.dict(sys.modules, {'internal_services.client': client}):
                runner = load_file(app + '_runner_under_test', app + '/js/runner.py')
            response = MagicMock(ok=True)
            response.json.return_value = {'signature': 'synthetic-result'}
            with patch.object(runner, 'post_script_request', return_value=response) as post:
                result = runner.generate_func('schnorrSign')({'wif': 'synthetic-key'})
                post.assert_called_once_with(app, {'function': 'schnorrSign', 'params': ({'wif': 'synthetic-key'},)})
                self.assertEqual(result, {'signature': 'synthetic-result'})


if __name__ == '__main__':
    unittest.main()
