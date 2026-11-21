from unittest import TestCase

from main.utils.logging import REDACTED_VALUE, redact_mapping


class LoggingRedactionTests(TestCase):
    def test_sensitive_subscription_fields_are_redacted(self):
        values = {
            'address': 'bitcoincash:qexample',
            'webhook_url': 'https://merchant.example/webhook/',
            'webhook_secret': 'synthetic-webhook-secret',
            'current_webhook_secret': 'synthetic-current-secret',
            'new_webhook_secret': 'synthetic-new-secret',
        }
        result = redact_mapping(values, {
            'webhook_secret',
            'current_webhook_secret',
            'new_webhook_secret',
        })
        self.assertEqual(result['address'], values['address'])
        self.assertEqual(result['webhook_url'], values['webhook_url'])
        for key in ('webhook_secret', 'current_webhook_secret', 'new_webhook_secret'):
            self.assertEqual(result[key], REDACTED_VALUE)
            self.assertNotIn(values[key], repr(result))

    def test_input_mapping_is_not_mutated(self):
        values = {'webhook_secret': 'synthetic-secret'}
        redact_mapping(values, {'webhook_secret'})
        self.assertEqual(values['webhook_secret'], 'synthetic-secret')
