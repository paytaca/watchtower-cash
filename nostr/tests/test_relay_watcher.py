from unittest.mock import patch
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
    """Recipients for a kind-445 MLS group event are resolved from the in-memory
    cache built from the room registry (h tag -> nostr_group_id -> members).
    The cache is rebuilt every PUBKEY_REFRESH_INTERVAL seconds."""

    def setUp(self):
        self.command = Command()
        self.command._group_members_cache = {}

    def _room(self, wallet_hash, room_id, members, nostr_group_id=GROUP_ID, archived=False):
        return NostrRoom.objects.create(
            room_id=room_id,
            wallet_hash=wallet_hash,
            type="mls-group",
            name="Group",
            members=members,
            nostr_group_id=nostr_group_id,
            archived=archived,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )

    def _refresh(self):
        self.command._refresh_group_cache()

    def test_returns_union_of_members_across_room_rows(self):
        self._room("wh_a", "room_a", [MEMBER_A, MEMBER_B])
        self._room("wh_b", "room_b", [MEMBER_B, MEMBER_C])

        self._refresh()

        recipients = self.command.get_group_recipient_pubkeys(
            GROUP_ID, {MEMBER_A, MEMBER_B, MEMBER_C},
        )

        self.assertEqual(recipients, {MEMBER_A, MEMBER_B, MEMBER_C})

    def test_only_returns_registered_pubkeys(self):
        self._room("wh_a", "room_a", [MEMBER_A, UNREGISTERED])

        self._refresh()

        recipients = self.command.get_group_recipient_pubkeys(GROUP_ID, {MEMBER_A})

        self.assertEqual(recipients, {MEMBER_A})

    def test_unknown_group_id_returns_empty(self):
        self._room("wh_a", "room_a", [MEMBER_A])

        self._refresh()

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

        self._refresh()

        recipients = self.command.get_group_recipient_pubkeys(GROUP_ID, {MEMBER_A})

        self.assertEqual(recipients, set())

    def test_archived_rooms_excluded_from_cache(self):
        self._room("wh_a", "room_a", [MEMBER_A], archived=False)
        self._room("wh_a", "room_b", [MEMBER_B], archived=True)

        self._refresh()

        recipients = self.command.get_group_recipient_pubkeys(
            GROUP_ID, {MEMBER_A, MEMBER_B},
        )
        self.assertEqual(recipients, {MEMBER_A})

    def test_archive_drop_takes_effect_after_refresh(self):
        self._room("wh_a", "room_a", [MEMBER_A])
        self._refresh()
        self.assertEqual(
            self.command.get_group_recipient_pubkeys(GROUP_ID, {MEMBER_A}),
            {MEMBER_A},
        )

        NostrRoom.objects.filter(room_id="room_a").update(archived=True)

        self._refresh()

        self.assertEqual(
            self.command.get_group_recipient_pubkeys(GROUP_ID, {MEMBER_A}),
            set(),
        )

    def test_new_room_picks_up_after_refresh(self):
        self._refresh()
        self.assertEqual(
            self.command.get_group_recipient_pubkeys(GROUP_ID, {MEMBER_A}),
            set(),
        )

        self._room("wh_a", "new_room", [MEMBER_A])

        self._refresh()

        self.assertEqual(
            self.command.get_group_recipient_pubkeys(GROUP_ID, {MEMBER_A}),
            {MEMBER_A},
        )

    def test_non_list_members_skipped_with_warning(self):
        self._room("wh_a", "good_room", [MEMBER_A])
        self._room("wh_b", "bad_room", [MEMBER_B])
        # Bypass model/serializer validation by writing a dict via .update() —
        # reproduces the case where a legacy row has corrupt data.
        NostrRoom.objects.filter(room_id="bad_room").update(members={"not": "a list"})

        with self.assertLogs("nostr.management.commands.nostr_relay_watcher", level="WARNING") as cm:
            self._refresh()

        log = "\n".join(cm.output)
        self.assertIn("non-list members field", log)

        # The good row still resolves correctly; the bad one is skipped silently.
        self.assertEqual(
            self.command.get_group_recipient_pubkeys(GROUP_ID, {MEMBER_A, MEMBER_B}),
            {MEMBER_A},
        )

    def test_db_error_during_refresh_empties_cache(self):
        self._room("wh_a", "room_a", [MEMBER_A])
        self._refresh()
        self.assertEqual(
            self.command.get_group_recipient_pubkeys(GROUP_ID, {MEMBER_A}),
            {MEMBER_A},
        )

        with patch(
            "nostr.models.NostrRoom.objects.filter",
            side_effect=RuntimeError("simulated DB outage"),
        ):
            with self.assertLogs(
                "nostr.management.commands.nostr_relay_watcher", level="ERROR",
            ):
                self._refresh()

        self.assertEqual(self.command._group_members_cache, {})
        self.assertEqual(
            self.command.get_group_recipient_pubkeys(GROUP_ID, {MEMBER_A}),
            set(),
        )
