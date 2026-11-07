from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone

from nostr.management.commands.nostr_relay_watcher import Command
from nostr.models import NostrPubkey, NostrRoom


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

    def _room(self, wallet_hash, room_id, members, nostr_group_id=GROUP_ID,
              archived=False, muted=False):
        return NostrRoom.objects.create(
            room_id=room_id,
            wallet_hash=wallet_hash,
            type="mls-group",
            name="Group",
            members=members,
            nostr_group_id=nostr_group_id,
            archived=archived,
            muted=muted,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )

    def _pubkey(self, wallet_hash, pubkey_hex):
        return NostrPubkey.objects.create(
            wallet_hash=wallet_hash,
            pubkey_hex=pubkey_hex,
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

    def test_muted_wallet_pubkeys_excluded_from_group_recipients(self):
        self._room("wh_a", "room_a", [MEMBER_A, MEMBER_B], muted=True)
        self._pubkey("wh_a", MEMBER_A)

        self._refresh()

        recipients = self.command.get_group_recipient_pubkeys(
            GROUP_ID, {MEMBER_A, MEMBER_B},
        )

        # The muted row still contributes both members to the union, so only
        # the muted wallet's own pubkey is dropped.
        self.assertEqual(recipients, {MEMBER_B})

    def test_mute_only_excludes_muted_wallet_across_shared_group(self):
        self._room("wh_a", "room_a", [MEMBER_A, MEMBER_B], muted=True)
        self._room("wh_b", "room_b", [MEMBER_A, MEMBER_B], muted=False)
        self._pubkey("wh_a", MEMBER_A)
        self._pubkey("wh_b", MEMBER_B)

        self._refresh()

        recipients = self.command.get_group_recipient_pubkeys(
            GROUP_ID, {MEMBER_A, MEMBER_B},
        )

        self.assertEqual(recipients, {MEMBER_B})

    def test_multiple_muted_wallets_in_one_group_are_excluded(self):
        self._room("wh_a", "room_a", [MEMBER_A, MEMBER_B, MEMBER_C], muted=True)
        self._room("wh_b", "room_b", [MEMBER_A, MEMBER_B, MEMBER_C], muted=True)
        self._pubkey("wh_a", MEMBER_A)
        self._pubkey("wh_b", MEMBER_B)

        self._refresh()

        recipients = self.command.get_group_recipient_pubkeys(
            GROUP_ID, {MEMBER_A, MEMBER_B, MEMBER_C},
        )

        self.assertEqual(recipients, {MEMBER_C})

    def test_unmuting_restores_recipients_after_refresh(self):
        self._room("wh_a", "room_a", [MEMBER_A, MEMBER_B], muted=True)
        self._pubkey("wh_a", MEMBER_A)
        self._refresh()
        self.assertEqual(
            self.command.get_group_recipient_pubkeys(
                GROUP_ID, {MEMBER_A, MEMBER_B},
            ),
            {MEMBER_B},
        )

        NostrRoom.objects.filter(room_id="room_a").update(muted=False)
        self._refresh()

        self.assertEqual(
            self.command.get_group_recipient_pubkeys(
                GROUP_ID, {MEMBER_A, MEMBER_B},
            ),
            {MEMBER_A, MEMBER_B},
        )

    def test_muted_wallet_without_registered_pubkey_is_ignored(self):
        self._room("wh_a", "room_a", [MEMBER_A, MEMBER_B, MEMBER_C], muted=True)
        self._pubkey("wh_a", MEMBER_A)
        self._room("wh_b", "room_b", [MEMBER_A, MEMBER_B, MEMBER_C], muted=True)
        # wh_b has no NostrPubkey registration; there is nothing to subtract
        # for it, and it must not suppress wh_a's mute either.
        self._pubkey("wh_c", MEMBER_C)

        self._refresh()

        recipients = self.command.get_group_recipient_pubkeys(
            GROUP_ID, {MEMBER_A, MEMBER_B, MEMBER_C},
        )

        self.assertEqual(recipients, {MEMBER_B, MEMBER_C})
        self.assertEqual(
            self.command._group_muted_pubkeys[GROUP_ID], {MEMBER_A},
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


class GetGroupEventRecipientsTestCase(TestCase):
    """A group message must not be pushed back to the client that sent it.

    Kind-445 events are signed with an ephemeral key, so the sender is only
    identifiable through the ``sender`` tag the client adds with its chat
    pubkey."""

    def setUp(self):
        self.command = Command()
        self.command._group_members_cache = {}
        self.command._group_muted_pubkeys = {}
        NostrRoom.objects.create(
            room_id="room_a",
            wallet_hash="wh_a",
            type="mls-group",
            name="Group",
            members=[MEMBER_A, MEMBER_B, MEMBER_C],
            nostr_group_id=GROUP_ID,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        for member in (MEMBER_A, MEMBER_B, MEMBER_C):
            NostrPubkey.objects.create(wallet_hash=f"wh_{member[:2]}", pubkey_hex=member)
        self.command._refresh_group_cache()
        self.registered = {MEMBER_A, MEMBER_B, MEMBER_C}

    def test_sender_is_excluded(self):
        recipients = self.command.get_group_event_recipients(
            [["h", GROUP_ID], ["sender", MEMBER_A]], self.registered,
        )

        self.assertEqual(recipients, {MEMBER_B, MEMBER_C})

    def test_untagged_event_notifies_every_member(self):
        recipients = self.command.get_group_event_recipients(
            [["h", GROUP_ID]], self.registered,
        )

        self.assertEqual(recipients, self.registered)

    def test_sender_tag_is_case_insensitive(self):
        recipients = self.command.get_group_event_recipients(
            [["h", GROUP_ID], ["sender", MEMBER_A.upper()]], self.registered,
        )

        self.assertEqual(recipients, {MEMBER_B, MEMBER_C})

    def test_unknown_sender_tag_leaves_recipients_untouched(self):
        recipients = self.command.get_group_event_recipients(
            [["h", GROUP_ID], ["sender", UNREGISTERED]], self.registered,
        )

        self.assertEqual(recipients, self.registered)

    def test_sender_and_muted_wallet_both_excluded(self):
        # Muting is per wallet, so the muted room row needs a registered
        # pubkey for its wallet for the mute to subtract anything.
        NostrPubkey.objects.create(wallet_hash="wh_a", pubkey_hex=MEMBER_A)
        NostrRoom.objects.filter(room_id="room_a").update(muted=True)
        self.command._refresh_group_cache()

        recipients = self.command.get_group_event_recipients(
            [["h", GROUP_ID], ["sender", MEMBER_B]], self.registered,
        )

        # MEMBER_A muted the room, MEMBER_B sent it, MEMBER_C is the only
        # device that should get a push.
        self.assertEqual(recipients, {MEMBER_C})

    def test_missing_group_id_returns_empty(self):
        self.assertEqual(
            self.command.get_group_event_recipients([["sender", MEMBER_A]], self.registered),
            set(),
        )
