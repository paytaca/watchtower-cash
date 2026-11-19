import hashlib
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import ecdsa
from django.core.management import call_command
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from rampp2p.models import Arbiter, Peer, RegistrationChallenge, RegistrationRequestBucket, ReservedName
from rampp2p.registration import RegistrationThrottle, registration_client_ip
from rampp2p.views.view_registration import RegistrationChallengeView
from rampp2p.views.view_user import ArbiterView, PeerViewSet


@override_settings(
    P2P_REGISTRATION_PROXY_HOPS=0,
    P2P_REGISTRATION_IP_PER_MINUTE=1000, P2P_REGISTRATION_IP_PER_DAY=1000,
    P2P_REGISTRATION_KEY_PER_MINUTE=1000, P2P_REGISTRATION_KEY_PER_DAY=1000,
)
class RegistrationTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.key = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
        self.public_key = self.key.verifying_key.to_string('compressed').hex()
        self.wallet = 'synthetic-wallet'
        self.data = {'name': 'synthetic-peer', 'address': 'synthetic-address', 'address_path': '0/0'}
        for target, value in (
            ('rampp2p.models.Peer.get_trade_stats', {
                'trade_count': 0, 'completed_trades': 0, 'failed_trades': 0,
                'completion_rate': 0, 'rating': None,
            }),
            ('rampp2p.models.Arbiter.average_rating', None),
        ):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def challenge(self, account_type='peer', data=None, wallet=None, public_key=None, **headers):
        request = self.factory.post('/registration/challenge/', {
            'account_type': account_type, 'wallet_hash': wallet or self.wallet,
            'public_key': public_key or self.public_key, 'data': self.data if data is None else data,
        }, format='json', **headers)
        return RegistrationChallengeView.as_view()(request)

    def signed_headers(self, challenge, wallet=None, public_key=None):
        signature = self.key.sign(
            challenge.data['message'].encode(), hashfunc=hashlib.sha256,
            sigencode=ecdsa.util.sigencode_der,
        ).hex()
        return {
            'HTTP_WALLET_HASH': wallet or self.wallet,
            'HTTP_PUBLIC_KEY': public_key or self.public_key,
            'HTTP_SIGNATURE': signature,
            'HTTP_REGISTRATION_CHALLENGE': challenge.data['challenge_id'],
        }

    def register(self, challenge, account_type='peer', data=None, headers=None):
        request = self.factory.post('/unused/', self.data if data is None else data,
                                    format='json', **(headers or self.signed_headers(challenge)))
        if account_type == 'peer':
            return PeerViewSet.as_view({'post': 'create'})(request)
        return ArbiterView.as_view()(request)

    def test_peer_registration_uses_real_bound_signature_and_consumes_challenge(self):
        challenge = self.challenge()
        self.assertEqual(challenge.status_code, 201)
        response = self.register(challenge)
        self.assertEqual(response.status_code, 201)
        peer = Peer.objects.get(wallet_hash=self.wallet)
        self.assertEqual(peer.public_key, self.public_key)
        self.assertEqual(peer.address, self.data['address'])
        self.assertIsNotNone(RegistrationChallenge.objects.get(pk=challenge.data['challenge_id']).consumed_at)
        self.assertEqual(self.register(challenge).status_code, 403)
        self.assertEqual(Peer.objects.count(), 1)

    def test_signature_cannot_be_replayed_with_different_wallet_or_profile_data(self):
        challenge = self.challenge()
        for data in (
            {**self.data, 'name': 'changed-name'}, {**self.data, 'address': 'changed-address'},
            {**self.data, 'address_path': '1/1'},
        ):
            self.assertEqual(self.register(challenge, data=data).status_code, 403)
        headers = self.signed_headers(challenge, wallet='other-wallet')
        self.assertEqual(self.register(challenge, headers=headers).status_code, 403)
        self.assertFalse(Peer.objects.exists())

    def test_changed_key_account_type_or_challenge_cannot_reuse_signature(self):
        challenge = self.challenge()
        other_key = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1).verifying_key.to_string('compressed').hex()
        self.assertEqual(self.register(challenge, headers=self.signed_headers(challenge, public_key=other_key)).status_code, 403)
        second = self.challenge()
        headers = self.signed_headers(challenge)
        headers['HTTP_REGISTRATION_CHALLENGE'] = second.data['challenge_id']
        self.assertEqual(self.register(second, headers=headers).status_code, 403)
        arbiter_data = {**self.data, 'public_key': self.public_key}
        self.assertEqual(self.register(challenge, account_type='arbiter', data=arbiter_data).status_code, 403)
        self.assertFalse(Peer.objects.exists())
        self.assertFalse(Arbiter.objects.exists())

    def test_expired_future_client_timestamps_and_missing_challenges_do_not_bypass_expiry(self):
        challenge = self.challenge()
        RegistrationChallenge.objects.filter(pk=challenge.data['challenge_id']).update(expires_at=timezone.now() - timedelta(seconds=1))
        headers = self.signed_headers(challenge)
        headers['HTTP_TIMESTAMP'] = '9999999999999'
        self.assertEqual(self.register(challenge, headers=headers).status_code, 403)
        headers.pop('HTTP_REGISTRATION_CHALLENGE')
        self.assertEqual(self.register(challenge, headers=headers).status_code, 400)
        self.assertFalse(Peer.objects.exists())

    def test_challenges_are_random_and_expire_in_five_minutes(self):
        first, second = self.challenge(), self.challenge()
        self.assertNotEqual(first.data['challenge_id'], second.data['challenge_id'])
        self.assertNotEqual(first.data['message'], second.data['message'])
        stored = RegistrationChallenge.objects.get(pk=first.data['challenge_id'])
        self.assertAlmostEqual((stored.expires_at - stored.created_at).total_seconds(), 300, delta=2)

    def test_invalid_signatures_and_malformed_challenge_ids_create_nothing(self):
        challenge = self.challenge()
        headers = self.signed_headers(challenge)
        headers['HTTP_SIGNATURE'] = '00'
        self.assertEqual(self.register(challenge, headers=headers).status_code, 403)
        for value in ('not-a-uuid', ''):
            headers['HTTP_REGISTRATION_CHALLENGE'] = value
            self.assertEqual(self.register(challenge, headers=headers).status_code, 400)
        self.assertFalse(Peer.objects.exists())

    def test_arbiter_registration_requires_bound_challenge_and_defaults_disabled(self):
        data = {**self.data, 'public_key': self.public_key}
        challenge = self.challenge('arbiter', data=data)
        response = self.register(challenge, account_type='arbiter', data=data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Arbiter.objects.get(wallet_hash=self.wallet).is_disabled)
        self.assertEqual(self.register(challenge, account_type='arbiter', data=data).status_code, 403)
        self.assertEqual(Arbiter.objects.count(), 1)

    def test_invalid_profile_rolls_back_creation_and_challenge_consumption(self):
        data = {**self.data, 'address': ''}
        challenge = self.challenge(data=data)
        self.assertEqual(self.register(challenge, data=data).status_code, 400)
        self.assertFalse(Peer.objects.exists())
        self.assertIsNone(RegistrationChallenge.objects.get(pk=challenge.data['challenge_id']).consumed_at)

    def test_reserved_name_redemption_is_atomic_with_peer_creation(self):
        reserved = ReservedName.objects.create(name='reserved-name')
        data = {**self.data, 'name': 'reserved-' + reserved.key}
        challenge = self.challenge(data=data)
        with patch.object(ReservedName, 'save', side_effect=ValueError('synthetic-failure')):
            with self.assertRaises(ValueError):
                self.register(challenge, data=data)
        self.assertFalse(Peer.objects.exists())
        reserved.refresh_from_db()
        self.assertIsNone(reserved.peer_id)
        self.assertIsNone(RegistrationChallenge.objects.get(pk=challenge.data['challenge_id']).consumed_at)
        self.assertEqual(self.register(challenge, data=data).status_code, 201)
        reserved.refresh_from_db()
        self.assertEqual(reserved.peer_id, Peer.objects.get().pk)

    def test_existing_other_account_type_cannot_register(self):
        Arbiter.objects.create(name='existing', wallet_hash=self.wallet, public_key=self.public_key, address='synthetic-address')
        challenge = self.challenge()
        self.assertEqual(self.register(challenge).status_code, 400)
        self.assertFalse(Peer.objects.exists())

    def test_standard_and_legacy_header_spellings_work(self):
        challenge = self.challenge()
        headers = self.signed_headers(challenge)
        request = self.factory.post('/unused/', self.data, format='json', **headers)
        # Django's test factory maps hyphens and underscores to the same META
        # key; explicitly test header lookup with real HTTP-standard names.
        from types import SimpleNamespace
        from rampp2p.registration import registration_identity
        standard = SimpleNamespace(headers={'wallet-hash': self.wallet, 'public-key': self.public_key}, META={})
        self.assertEqual(registration_identity(standard, 'peer'), (self.wallet, self.public_key))
        self.assertEqual(PeerViewSet.as_view({'post': 'create'})(request).status_code, 201)

    def test_malformed_challenge_requests_are_rejected_without_issuing_challenges(self):
        for data in ([], None, 'not-an-object'):
            self.assertEqual(self.challenge(data=data if data is not None else '').status_code, 400)
        self.assertEqual(self.challenge(account_type='other').status_code, 400)
        self.assertEqual(self.challenge(public_key='00').status_code, 400)
        self.assertEqual(self.challenge(public_key='ff' * 33).status_code, 400)
        self.assertFalse(RegistrationChallenge.objects.exists())

    @override_settings(P2P_REGISTRATION_IP_PER_MINUTE=2)
    def test_ip_limit_is_shared_across_challenge_and_submission_and_returns_retry_after(self):
        challenge = self.challenge()
        self.assertEqual(self.register(challenge).status_code, 201)
        response = self.challenge(wallet='other-wallet')
        self.assertEqual(response.status_code, 429)
        self.assertIn('Retry-After', response)
        self.assertEqual(RegistrationChallenge.objects.count(), 1)

    @override_settings(P2P_REGISTRATION_IP_PER_MINUTE=1)
    def test_spoofed_forwarded_for_does_not_bypass_ip_limit(self):
        self.assertEqual(self.challenge(HTTP_X_FORWARDED_FOR='192.0.2.1').status_code, 201)
        self.assertEqual(self.challenge(HTTP_X_FORWARDED_FOR='192.0.2.2').status_code, 429)

    @override_settings(P2P_REGISTRATION_PROXY_HOPS=1, P2P_REGISTRATION_IP_PER_MINUTE=1)
    def test_distinct_clients_behind_one_proxy_have_separate_ip_buckets(self):
        for client in ('192.0.2.1', '192.0.2.2'):
            response = self.challenge(REMOTE_ADDR='172.18.0.1', HTTP_X_FORWARDED_FOR=client)
            self.assertEqual(response.status_code, 201)

    @override_settings(P2P_REGISTRATION_PROXY_HOPS=1, P2P_REGISTRATION_IP_PER_MINUTE=1)
    def test_same_client_keeps_its_limit_across_proxy_addresses(self):
        self.assertEqual(self.challenge(REMOTE_ADDR='172.18.0.1', HTTP_X_FORWARDED_FOR='192.0.2.1').status_code, 201)
        response = self.challenge(REMOTE_ADDR='172.19.0.1', HTTP_X_FORWARDED_FOR='192.0.2.1')
        self.assertEqual(response.status_code, 429)
        self.assertIn('Retry-After', response)

    @override_settings(P2P_REGISTRATION_PROXY_HOPS=1, P2P_REGISTRATION_IP_PER_MINUTE=1)
    def test_caller_supplied_prefix_cannot_rotate_the_real_client_bucket(self):
        self.assertEqual(self.challenge(HTTP_X_FORWARDED_FOR='198.51.100.1, 192.0.2.1').status_code, 201)
        self.assertEqual(self.challenge(HTTP_X_FORWARDED_FOR='198.51.100.2, 192.0.2.1').status_code, 429)

    @override_settings(P2P_REGISTRATION_PROXY_HOPS=2, P2P_REGISTRATION_IP_PER_MINUTE=1)
    def test_two_trusted_hops_ignore_untrusted_prefixes(self):
        first = self.challenge(HTTP_X_FORWARDED_FOR='198.51.100.1, 192.0.2.1, 10.0.0.1')
        second = self.challenge(HTTP_X_FORWARDED_FOR='198.51.100.2, 192.0.2.1, 10.0.0.1')
        distinct = self.challenge(HTTP_X_FORWARDED_FOR='198.51.100.3, 192.0.2.2, 10.0.0.1')
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(distinct.status_code, 201)

    @override_settings(P2P_REGISTRATION_PROXY_HOPS=1)
    def test_missing_or_invalid_trusted_proxy_ip_does_not_create_buckets(self):
        for forwarded in (None, '', 'invalid', '192.0.2.1:443', 'fe80::1%eth0'):
            headers = {} if forwarded is None else {'HTTP_X_FORWARDED_FOR': forwarded}
            with self.subTest(forwarded=forwarded):
                self.assertEqual(self.challenge(**headers).status_code, 400)
        self.assertFalse(RegistrationRequestBucket.objects.exists())
        self.assertFalse(RegistrationChallenge.objects.exists())

    @override_settings(P2P_REGISTRATION_PROXY_HOPS=2)
    def test_short_forwarded_chain_is_rejected_instead_of_sharing_proxy_bucket(self):
        self.assertEqual(self.challenge(HTTP_X_FORWARDED_FOR='192.0.2.1').status_code, 400)
        self.assertFalse(RegistrationRequestBucket.objects.exists())

    @override_settings(P2P_REGISTRATION_PROXY_HOPS=1, P2P_REGISTRATION_IP_PER_MINUTE=1)
    def test_equivalent_ipv6_spellings_share_a_bucket(self):
        self.assertEqual(self.challenge(HTTP_X_FORWARDED_FOR='2001:db8::1').status_code, 201)
        self.assertEqual(self.challenge(HTTP_X_FORWARDED_FOR='2001:0db8:0000:0000:0000:0000:0000:0001').status_code, 429)

    @override_settings(P2P_REGISTRATION_PROXY_HOPS=1, P2P_REGISTRATION_IP_PER_MINUTE=1)
    def test_ipv4_mapped_ipv6_cannot_bypass_ipv4_bucket(self):
        self.assertEqual(self.challenge(HTTP_X_FORWARDED_FOR='192.0.2.1').status_code, 201)
        self.assertEqual(self.challenge(HTTP_X_FORWARDED_FOR='::ffff:192.0.2.1').status_code, 429)

    @override_settings(P2P_REGISTRATION_PROXY_HOPS=1, P2P_REGISTRATION_IP_PER_MINUTE=2)
    def test_proxied_challenge_and_submission_share_the_client_bucket(self):
        challenge = self.challenge(REMOTE_ADDR='172.18.0.1', HTTP_X_FORWARDED_FOR='192.0.2.1')
        headers = self.signed_headers(challenge)
        headers['HTTP_X_FORWARDED_FOR'] = '192.0.2.1'
        self.assertEqual(self.register(challenge, headers=headers).status_code, 201)
        self.assertEqual(self.challenge(wallet='another-wallet', HTTP_X_FORWARDED_FOR='192.0.2.1').status_code, 429)

    def test_direct_mode_rejects_missing_or_invalid_socket_ip(self):
        for remote in ('', None, 'invalid'):
            with self.subTest(remote=remote):
                self.assertEqual(self.challenge(REMOTE_ADDR=remote).status_code, 400)
        self.assertFalse(RegistrationRequestBucket.objects.exists())

    def test_invalid_proxy_configuration_fails_closed(self):
        request = self.factory.post('/unused/', {}, format='json')
        for hops in (-1, 11, '1'):
            with self.subTest(hops=hops), override_settings(P2P_REGISTRATION_PROXY_HOPS=hops):
                with self.assertRaises(ImproperlyConfigured):
                    registration_client_ip(request)

    @override_settings(P2P_REGISTRATION_KEY_PER_MINUTE=1)
    def test_key_limit_applies_across_ips_and_account_types(self):
        self.assertEqual(self.challenge(REMOTE_ADDR='192.0.2.1').status_code, 201)
        self.assertEqual(self.challenge(account_type='arbiter', REMOTE_ADDR='192.0.2.2').status_code, 429)

    @override_settings(P2P_REGISTRATION_IP_PER_DAY=1)
    def test_daily_limit_applies_even_when_minute_bucket_has_room(self):
        self.assertEqual(self.challenge().status_code, 201)
        self.assertEqual(self.challenge(wallet='other-wallet').status_code, 429)

    @override_settings(P2P_REGISTRATION_IP_PER_MINUTE=1)
    def test_separate_throttle_instances_share_database_counters(self):
        from rest_framework.request import Request
        request = Request(self.factory.post('/unused/', {'public_key': self.public_key}, format='json'))
        # Allow DRF to parse JSON as it would inside either registration view.
        from rest_framework.parsers import JSONParser
        request.parsers = [JSONParser()]
        self.assertTrue(RegistrationThrottle().allow_request(request, None))
        self.assertFalse(RegistrationThrottle().allow_request(request, None))
        self.assertEqual(RegistrationRequestBucket.objects.filter(attempts__gt=1).count(), 0)

    def test_invalid_json_shape_is_rejected_by_throttle(self):
        request = self.factory.post('/registration/challenge/', [], format='json')
        self.assertEqual(RegistrationChallengeView.as_view()(request).status_code, 400)
        self.assertFalse(RegistrationRequestBucket.objects.exists())

    def test_cleanup_preserves_live_challenges_and_limits_batch_size(self):
        live = self.challenge()
        old = timezone.now() - timedelta(days=2)
        for _ in range(2):
            RegistrationChallenge.objects.create(account_type='peer', payload_digest='a' * 64, expires_at=old)
        RegistrationRequestBucket.objects.create(pk='expired', expires_at=old)
        call_command('prune_p2p_registration', batch_size=1, stdout=StringIO())
        self.assertTrue(RegistrationChallenge.objects.filter(pk=live.data['challenge_id']).exists())
        self.assertEqual(RegistrationChallenge.objects.filter(expires_at=old).count(), 1)
        self.assertFalse(RegistrationRequestBucket.objects.filter(pk='expired').exists())
