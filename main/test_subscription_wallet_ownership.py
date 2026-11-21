"""An address may only ever be linked to one wallet."""
from unittest.mock import patch

from django.test import TestCase

from main.models import Address, Wallet
from main.utils.subscription import new_subscription


class SubscriptionWalletOwnershipTests(TestCase):
    def setUp(self):
        self.wallet_a = Wallet.objects.create(
            wallet_hash='wallet-a', wallet_type='bch', version=2,
        )
        self.wallet_b = Wallet.objects.create(
            wallet_hash='wallet-b', wallet_type='bch', version=2,
        )

        for target, value in (
            ('is_bch_address', True),
            ('is_slp_address', False),
            ('is_token_address', False),
        ):
            patcher = patch('main.utils.subscription.' + target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

        patcher = patch(
            'main.utils.subscription.bch_address_converter',
            side_effect=lambda address, to_token_addr=True: address,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        for target in (
            'clear_last_address_index_cache',
            'get_bch_utxos',
            'get_slp_utxos',
            'publish_subscribed_addresses_to_mqtt_task',
        ):
            patcher = patch('main.utils.subscription.' + target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def subscribe(self, wallet_hash, address, index=0):
        return new_subscription(
            addresses={'receiving': address},
            wallet_hash=wallet_hash,
            address_index=index,
        )

    def test_another_wallet_cannot_claim_an_existing_address(self):
        self.assertTrue(self.subscribe('wallet-a', 'bitcoincash:qsynthetica')['success'])
        address = Address.objects.get(address='bitcoincash:qsynthetica')
        self.assertEqual(address.wallet_id, self.wallet_a.id)

        response = self.subscribe('wallet-b', 'bitcoincash:qsynthetica')

        self.assertFalse(response['success'])
        self.assertEqual(response['error'], 'address_already_owned')
        address.refresh_from_db()
        self.assertEqual(address.wallet_id, self.wallet_a.id)

    def test_the_same_wallet_can_subscribe_the_address_again(self):
        self.assertTrue(self.subscribe('wallet-a', 'bitcoincash:qsynthetica')['success'])

        response = self.subscribe('wallet-a', 'bitcoincash:qsynthetica')

        self.assertTrue(response['success'])
        address = Address.objects.get(address='bitcoincash:qsynthetica')
        self.assertEqual(address.wallet_id, self.wallet_a.id)

    def test_rejected_change_address_is_not_published_to_mqtt(self):
        self.assertTrue(self.subscribe('wallet-a', 'bitcoincash:qowned')['success'])
        with patch('main.utils.subscription.publish_subscribed_addresses_to_mqtt_task.delay') as publish:
            new_subscription(
                addresses={'receiving': 'bitcoincash:qfree', 'change': 'bitcoincash:qowned'},
                wallet_hash='wallet-b', address_index=1,
            )
        for call in publish.call_args_list:
            self.assertNotIn('bitcoincash:qowned', call.args[0])

    def test_an_unowned_address_can_be_claimed_by_either_wallet(self):
        self.assertTrue(self.subscribe('wallet-b', 'bitcoincash:qsyntheticb')['success'])

        address = Address.objects.get(address='bitcoincash:qsyntheticb')
        self.assertEqual(address.wallet_id, self.wallet_b.id)

    def test_a_request_without_a_wallet_does_not_change_ownership(self):
        self.assertTrue(self.subscribe('wallet-a', 'bitcoincash:qsynthetica')['success'])

        response = new_subscription(
            addresses={'receiving': 'bitcoincash:qsynthetica'},
            address_index=0,
        )

        self.assertTrue(response['success'])
        address = Address.objects.get(address='bitcoincash:qsynthetica')
        self.assertEqual(address.wallet_id, self.wallet_a.id)
