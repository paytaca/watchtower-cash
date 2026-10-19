from django.test import TestCase
from django.utils import timezone

from nostr.management.commands.nostr_relay_watcher import Command
from nostr.models import NostrRoom


GROUP_ID = "aa" * 32
OTHER_GROUP_ID = "bb" * 32
MEMBER_A = "a1" * 32
MEMBER_B = "b2" * 32
MEMBER_C = "c3" * 32
UNREGISTERED = "d4" * 32


class GetGroupRecipientPubkeysTestCase(TestCase):
    """Recipients for a kind-445 MLS group event are resolved from the room
    registry (h tag -> nostr_group_id -> members), not from the event itself."""

    def setUp(self):
        self.command = Command()

    def _room(self, wallet_hash, room_id, members, nostr_group_id=GROUP_ID):
        return NostrRoom.objects.create(
            room_id=room_id,
            wallet_hash=wallet_hash,
            type="mls-group",
            name="Group",
            members=members,
            nostr_group_id=nostr_group_id,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )

    def test_returns_union_of_members_across_room_rows(self):
        self._room("wh_a", "room_a", [MEMBER_A, MEMBER_B])
        self._room("wh_b", "room_b", [MEMBER_B, MEMBER_C])

        recipients = self.command.get_group_recipient_pubkeys(
            GROUP_ID, {MEMBER_A, MEMBER_B, MEMBER_C},
        )

        self.assertEqual(recipients, {MEMBER_A, MEMBER_B, MEMBER_C})

    def test_only_returns_registered_pubkeys(self):
        self._room("wh_a", "room_a", [MEMBER_A, UNREGISTERED])

        recipients = self.command.get_group_recipient_pubkeys(GROUP_ID, {MEMBER_A})

        self.assertEqual(recipients, {MEMBER_A})

    def test_unknown_group_id_returns_empty(self):
        self._room("wh_a", "room_a", [MEMBER_A])

        recipients = self.command.get_group_recipient_pubkeys(
            OTHER_GROUP_ID, {MEMBER_A},
        )

        self.assertEqual(recipients, set())

    def test_missing_group_id_returns_empty(self):
        self.assertEqual(self.command.get_group_recipient_pubkeys(None, {MEMBER_A}), set())
        self.assertEqual(self.command.get_group_recipient_pubkeys("", {MEMBER_A}), set())

    def test_ignores_rooms_without_group_id(self):
        NostrRoom.objects.create(
            room_id="private_room",
            wallet_hash="wh_a",
            type="private",
            name="DM",
            members=[MEMBER_A],
            nostr_group_id=None,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )

        recipients = self.command.get_group_recipient_pubkeys(GROUP_ID, {MEMBER_A})

        self.assertEqual(recipients, set())
