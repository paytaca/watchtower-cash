from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest import TestCase

from rampp2p.order_audit import audit_order, burst_order_ids, canonical_key


# Public secp256k1 generator, in compressed/uncompressed encodings.
KEY = '0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798'
UNCOMPRESSED = ('0479be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798'
                '483ada7726a3c4655da4fbfc0e1108a8fd17b448a68554199c47d08ffb10d4b8')


class OrderAuditTests(TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 17, tzinfo=timezone.utc)
        self.creator = NS(pk=1, name='Creator', wallet_hash='creator', public_key=KEY, address='creator-address')
        self.ad_owner = NS(pk=2, name='Ad owner', wallet_hash='ad-owner', public_key=KEY, address='seller-address')
        self.arbiter = NS(pk=3, name='Arbiter', wallet_hash='arbiter', public_key=KEY, address='arbiter-address')
        self.order = NS(
            pk=10, owner_id=1, owner=self.creator, arbiter=self.arbiter,
            tracking_id='synthetic', created_at=self.now, trade_amount=10000,
            is_cash_in=False, ad_snapshot=NS(ad_id=20, trade_type='SELL', ad=NS(owner=self.ad_owner)),
        )
        self.statuses = [self.status('SBM', pk=1), self.status('CNF', pk=2)]
        self.contract = NS(pk=30, address='synthetic-contract')
        self.members = [NS(member_type=role, member_ref_id=p.pk, pubkey=p.public_key, address=p.address)
                        for role, p in [('SELLER', self.ad_owner), ('BUYER', self.creator), ('ARBITER', self.arbiter)]]

    def status(self, status, actor='creator', pk=1, created_at=None):
        return NS(pk=pk, status=status, created_by=actor, created_at=created_at or self.now)

    def audit(self, contract=None, members=None, transactions=None):
        return audit_order(self.order, contract, self.statuses, members or [], transactions or [])

    def test_auto_confirmation_is_not_flagged_and_no_funding_is_unknown(self):
        row = self.audit()
        self.assertEqual(row['review_flags'], [])
        self.assertEqual(row['funding_evidence'], 'NO_FUNDING_RECORDED_NOT_VERIFIED_ON_CHAIN')
        self.assertEqual(row['order_trade_type'], 'BUY')

    def test_contract_profile_mismatches_are_flagged(self):
        self.members[0].pubkey = '03' + KEY[2:]
        self.members[0].address = 'changed-address'
        flags = self.audit(self.contract, self.members)['review_flags']
        self.assertIn('SELLER_CONTRACT_KEY_DIFFERS_FROM_CURRENT_PROFILE', flags)
        self.assertIn('SELLER_CONTRACT_ADDRESS_DIFFERS_FROM_CURRENT_PROFILE', flags)

    def test_equivalent_key_encodings_do_not_flag_a_mismatch(self):
        self.members[0].pubkey = UNCOMPRESSED.upper()
        self.assertEqual(canonical_key(KEY), canonical_key(UNCOMPRESSED))
        self.assertEqual(self.audit(self.contract, self.members)['review_flags'], [])

    def test_off_curve_raw_key_cannot_masquerade_as_registered_key(self):
        # Same x and y parity as KEY, but y=0 is not a point on secp256k1.
        self.members[0].pubkey = KEY[2:] + '00' * 32
        flags = self.audit(self.contract, self.members)['review_flags']
        self.assertIn('SELLER_INVALID_KEY_ENCODING', flags)

    def test_invalid_curve_points_and_missing_keys_are_rejected(self):
        for key in ('02' + 'ff' * 32, '00' * 64, '', None):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    canonical_key(key)

    def test_unsorted_statuses_use_earliest_submission_and_latest_status(self):
        self.statuses = [
            self.status('CNF', pk=3, created_at=self.now + timedelta(minutes=2)),
            self.status('SBM', 'ad-owner', pk=2, created_at=self.now + timedelta(minutes=1)),
            self.status('SBM', pk=1),
        ]
        row = self.audit()
        self.assertEqual(row['latest_status'], 'CNF')
        self.assertNotIn('SUBMITTED_ACTOR_DIFFERS_FROM_CREATOR', row['review_flags'])
        self.assertEqual([s['status'] for s in row['statuses']], ['SBM', 'SBM', 'CNF'])

    def test_status_timestamp_ties_are_ordered_by_primary_key(self):
        self.statuses = [self.status('CNF', pk=2), self.status('SBM', pk=1)]
        self.assertEqual(self.audit()['latest_status'], 'CNF')

    def test_missing_member_and_invalid_key_are_flagged(self):
        self.members[0].pubkey = 'invalid'
        self.members.pop()
        flags = self.audit(self.contract, self.members)['review_flags']
        self.assertIn('SELLER_INVALID_KEY_ENCODING', flags)
        self.assertIn('ARBITER_CONTRACT_MEMBER_MISSING_OR_DUPLICATE', flags)

    def test_unrelated_status_actor_and_missing_submission_are_flagged(self):
        self.statuses = [self.status('CNF', 'unrelated')]
        flags = self.audit()['review_flags']
        self.assertIn('MISSING_SUBMITTED_STATUS', flags)
        self.assertIn('STATUS_ACTOR_OUTSIDE_CURRENT_PARTICIPANTS', flags)

    def test_funding_evidence_requires_a_validated_txid(self):
        self.assertEqual(self.audit(transactions=[NS(action='ESCROW', txid=None, valid=False)])['funding_evidence'],
                         'NO_FUNDING_RECORDED_NOT_VERIFIED_ON_CHAIN')
        self.assertEqual(self.audit(transactions=[NS(action='ESCROW', txid='synthetic', valid=False)])['funding_evidence'],
                         'TRANSACTION_RECORDED_REVIEW_ON_CHAIN')
        self.assertEqual(self.audit(transactions=[NS(action='ESCROW', txid='synthetic', valid=True)])['funding_evidence'],
                         'VALIDATED_ESCROW_RECORDED')
        self.statuses.append(self.status('ESCRW'))
        self.assertEqual(self.audit()['funding_evidence'], 'POST_ESCROW_STATUS_REVIEW_ON_CHAIN')

    def test_sell_order_roles_are_opposite_buy_ad_roles(self):
        self.order.ad_snapshot.trade_type = 'BUY'
        row = self.audit()
        self.assertEqual(row['order_trade_type'], 'SELL')
        self.assertEqual(row['seller']['id'], self.creator.pk)

    def test_sliding_bursts_include_all_members_and_separate_creators(self):
        orders = [NS(pk=i, owner_id=1, created_at=self.now + timedelta(minutes=i)) for i in range(5)]
        orders.append(NS(pk=99, owner_id=2, created_at=self.now + timedelta(minutes=4)))
        self.assertEqual(burst_order_ids(orders, 5, 5), set(range(5)))
        self.assertEqual(burst_order_ids(orders, 5, 3), set())

    def test_unsorted_burst_input_matches_chronological_input(self):
        orders = [NS(pk=i, owner_id=1, created_at=self.now + timedelta(minutes=i)) for i in range(8)]
        self.assertEqual(burst_order_ids(reversed(orders), 5, 5), set(range(8)))
        sparse = [NS(pk=i, owner_id=1, created_at=self.now + timedelta(minutes=i * 10)) for i in range(5)]
        self.assertEqual(burst_order_ids(reversed(sparse), 3, 5), set())
