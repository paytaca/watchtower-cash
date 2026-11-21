"""An address may only ever be linked to one wallet."""
from unittest.mock import Mock, patch

from django.test import TestCase

from main.models import Address, Subscription, Wallet
from main.utils.recipient_handler import WebhookOwnershipRequired, WebhookSecretRegistrationRequired
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
            response = new_subscription(
                addresses={'receiving': 'bitcoincash:qfree', 'change': 'bitcoincash:qowned'},
                wallet_hash='wallet-b', address_index=1,
            )
        self.assertEqual(response, {'success': False, 'error': 'address_already_owned'})
        self.assertFalse(Subscription.objects.filter(
            address__address='bitcoincash:qowned', address__wallet=self.wallet_b,
        ).exists())
        publish.assert_not_called()

    def test_locked_ownership_conflict_overrides_previous_address_success(self):
        def locked_address(pk):
            address = Address.objects.get(pk=pk)
            if address.address == 'bitcoincash:qraced':
                # Simulate another wallet claiming the row between the first
                # ownership check and the locked re-check.
                address.wallet = self.wallet_a
                address.save(update_fields=['wallet'])
            return address

        with patch('main.utils.subscription.Address.objects.select_for_update') as lock:
            lock.return_value.get.side_effect = locked_address
            response = new_subscription(
                addresses={'receiving': 'bitcoincash:qfree', 'change': 'bitcoincash:qraced'},
                wallet_hash='wallet-b', address_index=1,
            )
        self.assertEqual(response, {'success': False, 'error': 'address_already_owned'})
        self.assertFalse(Subscription.objects.filter(address__address='bitcoincash:qraced').exists())

    def test_second_address_webhook_errors_override_previous_success(self):
        for index, (exception, error) in enumerate((
            (WebhookOwnershipRequired, 'webhook_url_already_has_secret'),
            (WebhookSecretRegistrationRequired, 'webhook_url_secret_not_registered'),
        )):
            with self.subTest(error=error), patch(
                'main.utils.subscription.RecipientHandler.get_or_create',
                side_effect=[(None, False), exception()],
            ), patch('main.utils.subscription.publish_subscribed_addresses_to_mqtt_task.delay') as publish:
                response = new_subscription(
                    addresses={
                        'receiving': f'bitcoincash:qfree{index}',
                        'change': f'bitcoincash:qchange{index}',
                    }, wallet_hash='wallet-b', address_index=index,
                )
            self.assertEqual(response, {'success': False, 'error': error})
            publish.assert_not_called()

    def test_invalid_change_address_overrides_previous_success(self):
        with patch('main.utils.subscription.is_bch_address', side_effect=lambda address: address != 'invalid'):
            response = new_subscription(
                addresses={'receiving': 'bitcoincash:qfree', 'change': 'invalid'},
                wallet_hash='wallet-b', address_index=1,
            )
        self.assertEqual(response, {'success': False, 'error': 'invalid_address'})

    def test_advance_subscription_rolls_back_half_claimed_pair(self):
        from main.views.view_advance_subscription import AdvanceSubscriptionViewSet

        new_subscription(
            addresses={'receiving': 'bitcoincash:qowned'},
            wallet_hash='wallet-a', address_index=1, advance_subscription=True,
        )
        owned = Address.objects.get(address='bitcoincash:qowned')
        original_subscriptions = Subscription.objects.count()

        # Also verify that the view defensively rejects the old contradictory
        # success=True/error result, even if a caller regresses in the future.
        for sticky_success in (False, True):
            with self.subTest(sticky_success=sticky_success):
                receiving = f'bitcoincash:qfree{sticky_success}'
                data = {
                    'wallet_hash': 'wallet-b', 'start_index': 1,
                    'address_pairs': [{'receiving': receiving, 'change': owned.address}],
                }

                def subscribe_pair(**kwargs):
                    result = new_subscription(**kwargs)
                    if sticky_success:
                        result['success'] = True
                    return result

                view = AdvanceSubscriptionViewSet()
                serializer = Mock(validated_data=data)
                serializer.is_valid.return_value = True
                with patch.object(view, 'get_serializer', return_value=serializer), patch(
                    'main.views.view_advance_subscription.new_subscription', side_effect=subscribe_pair,
                ):
                    response = view.create(Mock(data=data))

                self.assertEqual(response.data['subscribed'], 0)
                self.assertEqual(response.data['skipped'], 2)
                self.assertFalse(Address.objects.filter(address=receiving).exists())
                self.assertEqual(Subscription.objects.count(), original_subscriptions)
                owned.refresh_from_db()
                self.assertEqual(owned.wallet_id, self.wallet_a.id)
                self.assertTrue(owned.advance_subscription)

    def test_address_scan_stops_after_result_with_success_and_error(self):
        from main.views.view_address_scan import WalletAddressScanViewSet

        address_sets = [
            {'address_index': index, 'addresses': {
                'receiving': f'bitcoincash:qreceiving{index}',
                'change': f'bitcoincash:qchange{index}',
            }} for index in (0, 1)
        ]
        data = {'wallet_hash': 'wallet-b', 'address_sets': address_sets}
        serializer = Mock(validated_data=data)
        serializer.is_valid.return_value = True
        serializer.sorted_address_sets.return_value = address_sets
        view = WalletAddressScanViewSet()
        with patch.object(view, 'get_serializer', return_value=serializer), patch(
            'main.views.view_address_scan.NODE.BCH.check_addresses_history',
            return_value={address_sets[-1]['addresses']['receiving']: True},
        ), patch('main.views.view_address_scan.new_subscription', return_value={
            'success': True, 'error': 'address_already_owned',
        }) as subscribe:
            response = view.create(Mock(data=data))
        subscribe.assert_called_once()
        self.assertEqual([item['success'] for item in response.data], [False, False])
        self.assertEqual(response.data[0]['error'], 'address_already_owned')

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
