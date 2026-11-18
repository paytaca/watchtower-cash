from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from rampp2p.models import Ad, Peer
from rampp2p.serializers.serializer_ad import WriteAdSerializer


class AdOwnershipTests(SimpleTestCase):
    def setUp(self):
        self.owner = Peer(pk=1, wallet_hash='synthetic-owner')
        self.other_peer = Peer(pk=2, wallet_hash='synthetic-other-peer')
        self.ad = Ad(pk=10, owner=self.owner, description='Original description')

    def serializer(self, data, instance=None, resolved_owner=None):
        serializer = WriteAdSerializer(instance=instance, data=data)
        # Resolve synthetic peers without consulting an application database.
        queryset = Mock()
        queryset.get.return_value = resolved_owner
        serializer.fields['owner'].get_queryset = Mock(return_value=queryset)
        return serializer

    def test_owner_cannot_transfer_ad_to_another_peer(self):
        serializer = self.serializer(
            {'owner': self.other_peer.pk, 'description': 'Attempted transfer'},
            instance=self.ad, resolved_owner=self.other_peer,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('owner', serializer.errors)
        self.assertEqual(str(serializer.errors['owner'][0]), 'Ad ownership cannot be changed.')
        self.assertEqual(self.ad.owner_id, self.owner.pk)
        self.assertEqual(self.ad.description, 'Original description')

    def test_update_can_include_the_existing_owner(self):
        serializer = self.serializer(
            {'owner': self.owner.pk, 'description': 'Updated description'},
            instance=self.ad, resolved_owner=self.owner,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        with patch.object(Ad, 'save') as save:
            updated = serializer.save()

        save.assert_called_once_with()
        self.assertEqual(updated.owner_id, self.owner.pk)
        self.assertEqual(updated.description, 'Updated description')

    def test_update_without_owner_preserves_ownership(self):
        serializer = self.serializer(
            {'description': 'Updated description'}, instance=self.ad,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        with patch.object(Ad, 'save'):
            updated = serializer.save()

        serializer.fields['owner'].get_queryset.assert_not_called()
        self.assertEqual(updated.owner_id, self.owner.pk)
        self.assertEqual(updated.description, 'Updated description')

    def test_create_accepts_the_owner_assigned_by_the_view(self):
        serializer = self.serializer(
            {'owner': self.owner.pk, 'description': 'New ad'},
            resolved_owner=self.owner,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        with patch.object(Ad.objects, 'create', return_value=self.ad) as create:
            serializer.save()

        create.assert_called_once_with(owner=self.owner, description='New ad')
