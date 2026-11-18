from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from rampp2p.models import Arbiter, Peer
from rampp2p.serializers.serializer_arbiter import ArbiterSerializer
from rampp2p.serializers.serializer_peer import PeerCreateSerializer, PeerUpdateSerializer
from rampp2p.views.view_user import ArbiterView, PeerViewSet


class ProfileIdentityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.peer = Peer.objects.create(
            name='Synthetic peer', wallet_hash='synthetic-peer',
            public_key='synthetic-peer-key', address='synthetic-peer-address',
            address_path='0/0', chat_identity_id=10,
        )
        cls.arbiter = Arbiter.objects.create(
            name='Synthetic arbiter', wallet_hash='synthetic-arbiter',
            public_key='synthetic-arbiter-key', address='synthetic-arbiter-address',
            address_path='0/1', chat_identity_id=20, is_disabled=False,
        )

    def setUp(self):
        self.peer = Peer.objects.get(pk=self.peer.pk)
        self.arbiter = Arbiter.objects.get(pk=self.arbiter.pk)
        self.factory = APIRequestFactory()
        for target, value in (
            ('authentication.permissions.RampP2PIsAuthenticated.has_permission', True),
            ('rampp2p.models.Arbiter.average_rating', None),
        ):
            mocked = patch(target, return_value=value)
            mocked.start()
            self.addCleanup(mocked.stop)

    def request(self, account_type, user, data):
        request = self.factory.patch('/unused/', data, format='json')
        force_authenticate(request, user=user)
        if account_type == 'peer':
            return PeerViewSet.as_view({'patch': 'partial_update'})(request)
        return ArbiterView.as_view()(request)

    def assert_unchanged(self, instance, before):
        stored = type(instance).objects.values().get(pk=instance.pk)
        self.assertEqual(stored, before)

    def test_peer_identity_changes_are_rejected_without_partial_profile_writes(self):
        for field, value in (
            ('public_key', 'replacement-key'),
            ('address', 'replacement-address'),
            ('address_path', '1/1'),
        ):
            with self.subTest(field=field):
                before = Peer.objects.values().get(pk=self.peer.pk)
                response = self.request('peer', self.peer, {
                    field: value, 'name': 'Attempted peer rename',
                })
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)
                self.assert_unchanged(self.peer, before)

    def test_arbiter_identity_changes_are_rejected_without_partial_profile_writes(self):
        for field, value in (
            ('public_key', 'replacement-key'),
            ('address', 'replacement-address'),
            ('address_path', '1/1'),
            ('wallet_hash', 'replacement-wallet'),
        ):
            with self.subTest(field=field):
                before = Arbiter.objects.values().get(pk=self.arbiter.pk)
                response = self.request('arbiter', self.arbiter, {
                    field: value, 'name': 'Attempted arbiter rename',
                })
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)
                self.assert_unchanged(self.arbiter, before)

    def test_multiple_identity_changes_report_all_changed_fields(self):
        response = self.request('peer', self.peer, {
            'public_key': 'replacement-key', 'address': 'replacement-address',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('public_key', response.data)
        self.assertIn('address', response.data)

    def test_unchanged_peer_identity_can_be_echoed_during_metadata_update(self):
        response = self.request('peer', self.peer, {
            'public_key': self.peer.public_key, 'address': self.peer.address,
            'address_path': self.peer.address_path, 'name': 'Renamed synthetic peer',
        })
        self.assertEqual(response.status_code, 200)
        stored = Peer.objects.get(pk=self.peer.pk)
        self.assertEqual(stored.name, 'Renamed synthetic peer')
        self.assertEqual(stored.public_key, 'synthetic-peer-key')
        self.assertEqual(stored.address, 'synthetic-peer-address')

    def test_unchanged_arbiter_identity_can_be_echoed_during_metadata_update(self):
        response = self.request('arbiter', self.arbiter, {
            'public_key': self.arbiter.public_key, 'address': self.arbiter.address,
            'address_path': self.arbiter.address_path, 'wallet_hash': self.arbiter.wallet_hash,
            'name': 'Renamed synthetic arbiter',
        })
        self.assertEqual(response.status_code, 200)
        stored = Arbiter.objects.get(pk=self.arbiter.pk)
        self.assertEqual(stored.name, 'Renamed synthetic arbiter')
        self.assertEqual(stored.wallet_hash, 'synthetic-arbiter')
        self.assertEqual(stored.public_key, 'synthetic-arbiter-key')
        self.assertEqual(stored.address, 'synthetic-arbiter-address')

    def test_metadata_only_updates_still_work(self):
        for kind, account in (('peer', self.peer), ('arbiter', self.arbiter)):
            with self.subTest(kind=kind):
                response = self.request(kind, account, {'chat_identity_id': '99'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(type(account).objects.get(pk=account.pk).chat_identity_id, 99)

    def test_peer_cannot_use_arbiter_profile_update(self):
        before = Peer.objects.values().get(pk=self.peer.pk)
        response = self.request('arbiter', self.peer, {
            'wallet_hash': 'replacement-wallet', 'public_key': 'replacement-key',
        })
        self.assertEqual(response.status_code, 403)
        self.assert_unchanged(self.peer, before)

    def test_arbiter_cannot_use_peer_profile_update(self):
        before = Arbiter.objects.values().get(pk=self.arbiter.pk)
        response = self.request('peer', self.arbiter, {'public_key': 'replacement-key'})
        self.assertEqual(response.status_code, 403)
        self.assert_unchanged(self.arbiter, before)

    def test_partial_serializers_cannot_bypass_identity_validation(self):
        for serializer_class, account in (
            (PeerUpdateSerializer, self.peer), (ArbiterSerializer, self.arbiter),
        ):
            with self.subTest(serializer=serializer_class.__name__):
                serializer = serializer_class(
                    account, data={'address': 'replacement-address'}, partial=True,
                )
                self.assertFalse(serializer.is_valid())
                self.assertIn('address', serializer.errors)

    def test_stale_metadata_updates_do_not_restore_old_identity_fields(self):
        for kind, account in (('peer', self.peer), ('arbiter', self.arbiter)):
            with self.subTest(kind=kind):
                # Simulate an administrative identity change after authentication.
                model = type(account)
                model.objects.filter(pk=account.pk).update(
                    public_key='administratively-updated-key',
                    address='administratively-updated-address', address_path='1/2',
                )
                response = self.request(kind, account, {'chat_identity_id': '99'})
                self.assertEqual(response.status_code, 200)
                stored = model.objects.get(pk=account.pk)
                self.assertEqual(stored.public_key, 'administratively-updated-key')
                self.assertEqual(stored.address, 'administratively-updated-address')
                self.assertEqual(stored.address_path, '1/2')
                self.assertEqual(stored.chat_identity_id, 99)
                self.assertEqual(response.data['public_key'], stored.public_key)

    def test_stale_unchanged_identity_echoes_cannot_restore_old_keys(self):
        for kind, account in (('peer', self.peer), ('arbiter', self.arbiter)):
            with self.subTest(kind=kind):
                old_key = account.public_key
                type(account).objects.filter(pk=account.pk).update(public_key='newer-key')
                response = self.request(kind, account, {'public_key': old_key})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(type(account).objects.get(pk=account.pk).public_key, 'newer-key')
                self.assertEqual(response.data['public_key'], 'newer-key')

    def test_initial_identity_assignment_remains_available_for_registration(self):
        for serializer_class, model in (
            (PeerCreateSerializer, Peer), (ArbiterSerializer, Arbiter),
        ):
            with self.subTest(serializer=serializer_class.__name__):
                data = {
                    'name': 'New synthetic ' + model.__name__,
                    'wallet_hash': 'new-synthetic-' + model.__name__,
                    'public_key': 'new-synthetic-key', 'address': 'new-synthetic-address',
                    'address_path': '0/2',
                }
                serializer = serializer_class(data=data)
                self.assertTrue(serializer.is_valid(), serializer.errors)
                created = serializer.save()
                stored = model.objects.get(pk=created.pk)
                self.assertEqual(stored.public_key, data['public_key'])
                self.assertEqual(stored.address, data['address'])
                self.assertEqual(stored.wallet_hash, data['wallet_hash'])
