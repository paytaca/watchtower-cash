import base64
from datetime import datetime, timezone
from decimal import Decimal
import json
import pickle
from unittest import TestCase
from unittest.mock import Mock, patch

from rest_framework.renderers import JSONRenderer

from main.utils.history_cache import (
    pos_history_cache_key, pos_history_cache_params,
    read_history_cache, write_history_cache,
)


class HistoryCacheSecurityTests(TestCase):
    def test_json_round_trip_matches_uncached_api_rendering(self):
        data = {'results': [{'amount': Decimal('1.25'),
                             'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc)}]}
        cache = Mock()
        write_history_cache(cache, 'key', data, 300)
        args, kwargs = cache.set.call_args
        self.assertEqual(kwargs, {'ex': 300})
        cache.get.return_value = args[1].encode()
        restored = read_history_cache(cache, 'key')
        self.assertEqual(JSONRenderer().render(restored), JSONRenderer().render(data))

    def test_lists_and_empty_containers_are_supported(self):
        for value in ({}, [], {'results': []}, [{'amount': 1}]):
            with self.subTest(value=value):
                self.assertEqual(read_history_cache(Mock(get=Mock(return_value=json.dumps(value))), 'key'), value)

    def test_legacy_pickle_and_invalid_data_are_cache_misses_without_unpickling(self):
        legacy = pickle.dumps({'results': []})
        for value in (None, legacy, base64.b64encode(legacy), b'\xff', b'{',
                      'null', 'true', '42', '"scalar"'):
            with self.subTest(value=value), patch('pickle.loads', side_effect=AssertionError('Unsafe decode')):
                self.assertIsNone(read_history_cache(Mock(get=Mock(return_value=value)), 'key'))

    def test_unserializable_response_does_not_fall_back_to_pickle(self):
        for value in ({'value': object()}, {'value': float('nan')}, {'value': float('inf')}):
            cache = Mock()
            with self.subTest(value=value), patch('pickle.dumps', side_effect=AssertionError('Unsafe encode')):
                write_history_cache(cache, 'key', value, 300)
            cache.set.assert_not_called()

    def test_pos_keys_are_canonical_and_can_be_decoded_for_invalidation(self):
        params = {'posid': '12', 'page': '2'}
        first = pos_history_cache_key('synthetic-wallet', params)
        second = pos_history_cache_key('synthetic-wallet', {'page': '2', 'posid': '12'})
        self.assertEqual(first, second)
        self.assertEqual(pos_history_cache_params(first.encode()), params)
        self.assertNotEqual(first, pos_history_cache_key('synthetic-wallet', {'posid': '13', 'page': '2'}))

    def test_pos_key_parser_rejects_legacy_pickle_and_malformed_keys(self):
        legacy = base64.b64encode(pickle.dumps({'posid': '12'})).decode()
        keys = (
            'wallet:history:w:pos:' + legacy,
            'wallet:history:w:pos:json-v1:' + legacy,
            'wallet:history:w:pos:json-v1:!!!!',
            'wallet:history:w:pos:json-v1:' + base64.b64encode(b'[]').decode(),
            pos_history_cache_key('w', {'posid': '12'}) + ':count',
            b'\xff', None,
        )
        for key in keys:
            with self.subTest(key=key), patch('pickle.loads', side_effect=AssertionError('Unsafe decode')):
                self.assertIsNone(pos_history_cache_params(key))
