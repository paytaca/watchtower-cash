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

    def test_helper_get_and_post_requests_use_their_own_tokens(self):
        for service, variable, port in [
            ('address', 'ADDRESS_JS_AUTH_TOKEN', 3000),
            ('cts', 'CTS_JS_AUTH_TOKEN', 3001),
            ('multisig', 'MULTISIG_JS_AUTH_TOKEN', 3004),
        ]:
            for method in ['GET', 'POST']:
                with self.subTest(service=service, method=method), patch.object(client, 'config', return_value=TOKEN) as config, patch.object(client.requests, 'Session') as factory:
                    session = factory.return_value.__enter__.return_value
                    client.service_request(service, method, '/test/path', timeout=20, params={'test': 'value'})
                    config.assert_called_once_with(variable, default='')
                    self.assertFalse(session.trust_env)
                    getattr(session, method.lower()).assert_called_once_with(
                        'http://127.0.0.1:{}/test/path'.format(port),
                        headers={'Authorization': 'Bearer ' + TOKEN}, timeout=20,
                        allow_redirects=False, params={'test': 'value'},
                    )

    def test_absolute_urls_and_network_paths_are_rejected_before_sending_tokens(self):
        for path in ['http://untrusted.example/', '//untrusted.example/', 'relative']:
            with patch.object(client.requests, 'Session') as session:
                with self.assertRaises(ValueError):
                    client.service_request('multisig', 'GET', path)
                session.assert_not_called()

    def test_multisig_wrappers_preserve_methods_and_payloads(self):
        django_conf = types.ModuleType('django.conf')
        django_conf.settings = types.SimpleNamespace(MULTISIG={})
        with patch.dict(sys.modules, {'internal_services.client': client, 'django.conf': django_conf}):
            multisig = load_file('multisig_client_under_test', 'multisig/js_client.py')
        calls = [
            ('get_transaction_hash', ('abcd',), 'POST', '/multisig/utils/get-transaction-hash', {'data': {'transaction': 'abcd'}}),
            ('get_unsigned_transaction_hash', ('abcd',), 'GET', '/multisig/transaction/unsigned-transaction-hash?transaction_hex=abcd', {}),
            ('finalize_transaction', ({'tx': 1}, {'wallet': 2}), 'POST', '/multisig/transaction/finalize', {'json': {'multisigWallet': {'wallet': 2}, 'multisigTransaction': {'tx': 1}}}),
            ('get_signing_progress', ({'tx': 1}, {'wallet': 2}), 'POST', '/multisig/transaction/get-signing-progress', {'json': {'multisigWallet': {'wallet': 2}, 'multisigTransaction': {'tx': 1}}}),
            ('get_wallet_utxos', ('test-address',), 'GET', '/multisig/wallet/utxos?address=test-address', {}),
            ('verify_signature', ('test', 'pubkey', {'sig': 1}), 'POST', '/multisig/message/verify-signature', {'json': {'message': 'test', 'publicKey': 'pubkey', 'signature': {'sig': 1}, 'encoding': 'utf8'}}),
            ('decode_proposal', ('test', 'hex'), 'POST', '/multisig/transaction/decode-proposal', {'json': {'proposal': 'test', 'proposal_format': 'hex'}}),
            ('decode_psbt', ('test',), 'POST', '/multisig/transaction/decode-psbt', {'json': {'psbt': 'test'}}),
            ('combine_psbts', (['one', 'two'],), 'POST', '/multisig/transaction/combine-psbts', {'json': {'psbts': ['one', 'two']}}),
        ]
        for function, args, method, path, kwargs in calls:
            with self.subTest(function=function), patch.object(multisig, 'service_request') as request:
                self.assertIs(getattr(multisig, function)(*args), request.return_value)
                request.assert_called_once_with('multisig', method, path, timeout=20, **kwargs)
        multisig.MULTISIG_JS_SERVER = 'http://untrusted.example/'
        with patch.object(multisig, 'service_request') as request:
            with self.assertRaises(ImproperlyConfigured):
                multisig.get_wallet_utxos('test')
            request.assert_not_called()

    def test_address_helpers_preserve_results_and_use_authenticated_transport(self):
        cashaddress = types.ModuleType('cashaddress')
        cashaddress.convert = types.SimpleNamespace(to_cash_address=lambda address: address)
        bitcoin = types.ModuleType('bitcoin')
        django_conf = types.ModuleType('django.conf')
        django_conf.settings = types.SimpleNamespace(BCH_NETWORK='mainnet')
        stubs = {'internal_services.client': client, 'cashaddress': cashaddress, 'bitcoin': bitcoin, 'django.conf': django_conf}
        with patch.dict(sys.modules, stubs):
            converter = load_file('converter_under_test', 'main/utils/address_converter.py')
            validator = load_file('validator_under_test', 'main/utils/address_validator.py')
            scan = load_file('scan_under_test', 'main/utils/address_scan.py')
        response = MagicMock(status_code=200, text='converted-address')
        with patch.object(converter, 'service_request', return_value=response) as request:
            self.assertEqual(converter.bch_address_converter('test-address'), 'converted-address')
            request.assert_called_once_with('address', 'GET', '/convert-address/test-address?to_token=True')
        response.json.return_value = {'success': True, 'bytecode': 'abcd'}
        with patch.object(converter, 'service_request', return_value=response) as request:
            self.assertEqual(converter.address_to_locking_bytecode('test-address'), 'abcd')
            request.assert_called_once_with('address', 'GET', '/to-locking-bytecode/test-address')
        response.json.return_value = {'valid': True}
        with patch.object(validator, 'service_request', return_value=response) as request:
            self.assertTrue(validator.is_bch_address('test-address'))
            request.assert_called_once_with('address', 'GET', '/validate-address/test-address?token=False')
        response.json.return_value = [{'tx_hash': 'synthetic'}]
        with patch.object(scan, 'service_request', return_value=response) as request:
            self.assertEqual(scan.get_bch_transactions('test-address', chipnet=True), [{'tx_hash': 'synthetic'}])
            request.assert_called_once_with('address', 'GET', '/get-transactions/test-address/', params={'network': 'chipnet'})

    def test_cts_authentication_failures_propagate_instead_of_returning_partial_results(self):
        import requests
        with patch.dict(sys.modules, {'internal_services.client': client}):
            cts = load_file('cts_client_under_test', 'cts/js_client.py')
        response = MagicMock()
        response.raise_for_status.side_effect = requests.HTTPError('401 Unauthorized')
        with patch.object(cts, 'service_request', return_value=response):
            with self.assertRaises(requests.HTTPError):
                cts.get_token_authguard_addresses(['first', 'second'])
        response.raise_for_status.side_effect = None
        response.json.return_value = {'category': 'address'}
        with patch.object(cts, 'service_request', return_value=response) as request:
            self.assertEqual(cts.get_token_authguard_addresses(['test/category']), [{'category': 'address'}])
            request.assert_called_once_with('cts', 'GET', '/cts/js/authguard-token-deposit-address/test%2Fcategory')

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
