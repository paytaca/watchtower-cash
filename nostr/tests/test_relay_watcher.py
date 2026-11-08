from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone

from nostr.management.commands.nostr_relay_watcher import Command
from nostr.models import NostrPubkey, NostrRoom
from nostr.utils.rooms import ROOM_PUSH_TOKEN_TAG, room_push_token


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

    def test_archived_wallet_excluded_but_membership_kept(self):
        # Real group rows each carry the full member list, so the archived
        # wallet's pubkey keeps arriving through the other member's row.
        # Archiving must silence that wallet without truncating the union.
        self._room("wh_a", "room_a", [MEMBER_A, MEMBER_B], archived=True)
        self._room("wh_b", "room_b", [MEMBER_A, MEMBER_B])
        self._pubkey("wh_a", MEMBER_A)
        self._pubkey("wh_b", MEMBER_B)

        self._refresh()

        self.assertEqual(
            self.command._group_members_cache[GROUP_ID], {MEMBER_A, MEMBER_B},
        )
        recipients = self.command.get_group_recipient_pubkeys(
            GROUP_ID, {MEMBER_A, MEMBER_B},
        )
        self.assertEqual(recipients, {MEMBER_B})

    def test_archive_drop_takes_effect_after_refresh(self):
        self._room("wh_a", "room_a", [MEMBER_A, MEMBER_B])
        self._room("wh_b", "room_b", [MEMBER_A, MEMBER_B])
        self._pubkey("wh_a", MEMBER_A)
        self._pubkey("wh_b", MEMBER_B)
        self._refresh()
        self.assertEqual(
            self.command.get_group_recipient_pubkeys(
                GROUP_ID, {MEMBER_A, MEMBER_B},
            ),
            {MEMBER_A, MEMBER_B},
        )

        NostrRoom.objects.filter(room_id="room_a").update(archived=True)

        self._refresh()

        self.assertEqual(
            self.command.get_group_recipient_pubkeys(
                GROUP_ID, {MEMBER_A, MEMBER_B},
            ),
            {MEMBER_B},
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

    def test_archived_wallet_is_excluded(self):
        # Archiving implies muting: the wallet that archived the group must not
        # receive pushes for it, while the other members still do.
        NostrPubkey.objects.create(wallet_hash="wh_a", pubkey_hex=MEMBER_A)
        NostrRoom.objects.filter(room_id="room_a").update(archived=True)
        self.command._refresh_group_cache()

        recipients = self.command.get_group_event_recipients(
            [["h", GROUP_ID], ["sender", MEMBER_B]], self.registered,
        )

        self.assertEqual(recipients, {MEMBER_C})

    def test_missing_group_id_returns_empty(self):
        self.assertEqual(
            self.command.get_group_event_recipients([["sender", MEMBER_A]], self.registered),
            set(),
        )


class GetGiftWrapRecipientsTestCase(TestCase):
    """Mute filtering for gift-wrapped DMs and legacy group messages.

    The relay cannot see the room on a NIP-17 gift-wrap, so the sender adds an
    opaque room push token to the outer wrap. Only wallets that muted that room
    lose the push."""

    ROOM_ID = "dm-room-a-b"
    EPHEMERAL_PUBKEY = "ee" * 32

    def setUp(self):
        self.command = Command()
        self.command._group_members_cache = {}
        self.command._group_muted_pubkeys = {}
        self.command._room_muted_pubkeys = {}
        self.token = room_push_token(self.ROOM_ID)
        self.registered = {MEMBER_A, MEMBER_B}

    def _room(self, wallet_hash, room_id=None, muted=False, archived=False):
        return NostrRoom.objects.create(
            room_id=room_id or self.ROOM_ID,
            wallet_hash=wallet_hash,
            type="private",
            name="DM",
            members=[MEMBER_A, MEMBER_B],
            nostr_group_id=None,
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

    def _tags(self, token=None):
        tags = [["p", MEMBER_A], ["p", MEMBER_B]]
        if token:
            tags.append([ROOM_PUSH_TOKEN_TAG, token])
        return tags

    def _recipients(self, token=None):
        return self.command.get_gift_wrap_recipients(
            self._tags(token), self.EPHEMERAL_PUBKEY, self.registered,
        )

    def test_muted_wallet_excluded_without_affecting_the_other_member(self):
        self._pubkey("wh_a", MEMBER_A)
        self._pubkey("wh_b", MEMBER_B)
        self._room("wh_a", muted=True)
        self._room("wh_b")

        self.command._refresh_group_cache()

        self.assertEqual(self._recipients(self.token), {MEMBER_B})

    def test_unmuted_room_notifies_both_members(self):
        self._pubkey("wh_a", MEMBER_A)
        self._pubkey("wh_b", MEMBER_B)
        self._room("wh_a")
        self._room("wh_b")

        self.command._refresh_group_cache()

        self.assertEqual(self._recipients(self.token), {MEMBER_A, MEMBER_B})

    def test_archived_room_is_treated_as_muted(self):
        self._pubkey("wh_a", MEMBER_A)
        self._pubkey("wh_b", MEMBER_B)
        self._room("wh_a", archived=True)
        self._room("wh_b")

        self.command._refresh_group_cache()

        self.assertEqual(self._recipients(self.token), {MEMBER_B})

    def test_without_push_token_notifies_both_members(self):
        self._pubkey("wh_a", MEMBER_A)
        self._pubkey("wh_b", MEMBER_B)
        self._room("wh_a", muted=True)
        self._room("wh_b")

        self.command._refresh_group_cache()

        # Older clients do not send the tag; they keep the previous behaviour.
        self.assertEqual(self._recipients(), {MEMBER_A, MEMBER_B})

    def test_token_for_a_different_room_does_not_suppress(self):
        self._pubkey("wh_a", MEMBER_A)
        self._pubkey("wh_b", MEMBER_B)
        self._room("wh_a", room_id="some-other-room", muted=True)
        self._room("wh_b")

        self.command._refresh_group_cache()

        self.assertEqual(self._recipients(self.token), {MEMBER_A, MEMBER_B})

    def test_muted_wallet_without_registered_pubkey_is_ignored(self):
        self._pubkey("wh_b", MEMBER_B)
        self._room("wh_a", muted=True)
        self._room("wh_b")

        self.command._refresh_group_cache()

        # wh_a has no push identity, so there is nothing to subtract.
        self.assertEqual(self._recipients(self.token), {MEMBER_A, MEMBER_B})

    def test_empty_tags_resolves_no_recipients(self):
        self.assertEqual(
            self.command.get_gift_wrap_recipients(
                [], self.EPHEMERAL_PUBKEY, self.registered,
            ),
            set(),
        )

    def test_archived_dm_is_treated_as_muted(self):
        # Archiving a DM must silence the wallet that archived it even when the
        # explicit muted flag is still false.
        self._pubkey("wh_a", MEMBER_A)
        self._pubkey("wh_b", MEMBER_B)
        self._room("wh_a", archived=True)
        self._room("wh_b")

        self.command._refresh_group_cache()

        self.assertEqual(self._recipients(self.token), {MEMBER_B})
