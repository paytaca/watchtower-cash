from pathlib import Path
import subprocess
from unittest import TestCase
from unittest.mock import Mock, patch

from rampp2p.contract_generation import generate_contract_address


class ContractGenerationSecurityTests(TestCase):
    public_key = '0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798'

    def params(self, **changes):
        params = dict(
            arbiter_pubkey=self.public_key, buyer_pubkey=self.public_key,
            seller_pubkey=self.public_key, timestamp=1795132800.123456,
            service_fee=1000, arbitration_fee=2000,
        )
        params.update(changes)
        return params

    @patch('rampp2p.contract_generation.subprocess.run')
    def test_valid_generation_preserves_constructor_arguments_and_result(self, run):
        run.return_value = Mock(stdout=b'{"success":"true","contract_address":"synthetic"}\n', stderr=b'')
        response = generate_contract_address(**self.params())
        args, kwargs = run.call_args
        command = args[0]
        self.assertEqual(command[0], 'node')
        self.assertEqual(Path(command[1]), Path(__file__).resolve().parent / 'js/src/escrow.js')
        self.assertEqual(command[2:], [self.public_key] * 3 + ['1795132800.123456', '1000', '2000'])
        self.assertFalse(kwargs['shell'])
        self.assertTrue(kwargs['check'])
        self.assertEqual(kwargs['timeout'], 30)
        self.assertEqual(response, {'result': {'success': 'true', 'contract_address': 'synthetic'}, 'error': ''})

    @patch('rampp2p.contract_generation.subprocess.run')
    def test_bad_keys_never_start_a_process(self, run):
        for field in ('arbiter_pubkey', 'buyer_pubkey', 'seller_pubkey'):
            for value in (None, '', '--eval', self.public_key + ' injected',
                          '02' + 'ff' * 32, '04' + self.public_key[2:]):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    generate_contract_address(**self.params(**{field: value}))
        run.assert_not_called()

    @patch('rampp2p.contract_generation.subprocess.run')
    def test_bad_timestamps_never_start_a_process(self, run):
        for value in (None, True, -1, float('nan'), float('inf'), '--eval',
                      '1; injected', '1 2', '999999999999', [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                generate_contract_address(**self.params(timestamp=value))
        run.assert_not_called()

    @patch('rampp2p.contract_generation.subprocess.run')
    def test_bad_fees_never_start_a_process(self, run):
        for field in ('service_fee', 'arbitration_fee'):
            for value in (None, True, -1, 1.5, '1000', '--eval', 2100000000000001):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    generate_contract_address(**self.params(**{field: value}))
        run.assert_not_called()

    @patch('rampp2p.contract_generation.subprocess.run')
    def test_integer_valued_float_timestamp_keeps_its_hash_input(self, run):
        run.return_value = Mock(stdout=b'{"success":"true"}', stderr=b'')
        generate_contract_address(**self.params(timestamp=1795132800.0, service_fee=0))
        self.assertEqual(run.call_args[0][0][-3:], ['1795132800.0', '0', '2000'])

    @patch('rampp2p.contract_generation.subprocess.run')
    def test_process_failures_are_not_reported_as_success(self, run):
        for error in (subprocess.TimeoutExpired('node', 30), subprocess.CalledProcessError(1, 'node')):
            run.side_effect = error
            with self.subTest(error=error), self.assertRaises(type(error)):
                generate_contract_address(**self.params())

    @patch('rampp2p.contract_generation.subprocess.run')
    def test_invalid_generator_output_is_rejected(self, run):
        for output in (b'[]', b'null', b'not json'):
            run.return_value = Mock(stdout=output, stderr=b'')
            with self.subTest(output=output), self.assertRaises(ValueError):
                generate_contract_address(**self.params())


class ContractErrorCallbackTests(TestCase):
    def test_contract_creation_attaches_order_to_error_callback(self):
        from rampp2p.utils.contract import create_contract
        with patch('rampp2p.utils.contract.generate_contract.apply_async') as dispatch:
            create_contract(order_id=123)
        callback = dispatch.call_args.kwargs['link_error']
        self.assertEqual(callback.task, 'rampp2p.tasks.task_contract.contract_error_handler')
        self.assertEqual(callback.kwargs, {'order_id': 123})

    def test_generator_failure_notifies_without_exception_details(self):
        from rampp2p.tasks.task_contract import contract_error_handler
        with patch('rampp2p.tasks.task_contract.order_is_canceled', return_value=False), \
                patch('rampp2p.tasks.task_contract.send_order_update') as notify:
            contract_error_handler.run(Mock(), ValueError('sensitive-output'), None, order_id=123)
        payload, order_id = notify.call_args.args
        self.assertEqual(order_id, 123)
        self.assertFalse(payload['success'])
        self.assertNotIn('sensitive-output', str(payload))

    def test_cancellation_takes_priority_over_generator_failure(self):
        from rampp2p.contract_access import canceled_contract_payload
        from rampp2p.tasks.task_contract import contract_error_handler
        with patch('rampp2p.tasks.task_contract.order_is_canceled', return_value=True), \
                patch('rampp2p.tasks.task_contract.send_order_update') as notify:
            contract_error_handler.run(Mock(), ValueError('failure'), None, order_id=123)
        notify.assert_called_once_with(canceled_contract_payload(), 123)
