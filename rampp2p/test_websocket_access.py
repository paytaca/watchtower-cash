from datetime import timedelta
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from cryptography.fernet import Fernet
from django.conf import settings
from django.test import TransactionTestCase, override_settings
from django.urls import Resolver404, resolve
from django.utils import timezone

from authentication.models import AuthToken
from rampp2p.consumers import PrivateUpdatesConsumer
from rampp2p.models import Ad, AdSnapshot, Arbiter, CryptoCurrency, FiatCurrency, Order, OrderMember, Peer, Status, FeatureControl
from rampp2p.routing import websocket_urlpatterns
from rampp2p.utils.websocket import general_room_name, send_general_update


@override_settings(
    CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}},
    FERNET_KEY=Fernet.generate_key(),
)
class WebsocketAccessTests(TransactionTestCase):
    def setUp(self):
        def peer(pk, name):
            return Peer.objects.create(
                pk=pk, name=name, wallet_hash='synthetic_' + name.replace('-', '_'),
                public_key='synthetic-key', address='synthetic-address',
            )
        self.buyer = peer(1, 'buyer')
        self.seller = peer(2, 'seller')
        self.outsider = peer(3, 'outsider')
        self.arbiter = Arbiter.objects.create(
            pk=1, name='assigned', wallet_hash='synthetic_arbiter',
            public_key='synthetic-key', address='synthetic-address', is_disabled=False,
        )
        self.other_arbiter = Arbiter.objects.create(
            pk=2, name='unassigned', wallet_hash='synthetic_other_arbiter',
            public_key='synthetic-key', address='synthetic-address', is_disabled=False,
        )
        self.tokens = {}
        for user in (self.buyer, self.seller, self.outsider, self.arbiter, self.other_arbiter):
            token = 'synthetic-token-' + user.wallet_hash
            self.tokens[user.wallet_hash] = token
            AuthToken.objects.create(
                wallet_hash=user.wallet_hash,
                key=Fernet(settings.FERNET_KEY).encrypt(token.encode()).decode(),
                key_expires_at=timezone.now() + timedelta(hours=1),
            )
        fiat = FiatCurrency.objects.create(name='Synthetic fiat', symbol='TST')
        crypto = CryptoCurrency.objects.create(name='Synthetic BCH', symbol='TESTBCH')
        with patch('rampp2p.signals.AdSummaryMessage.send_safe'):
            ad = Ad.objects.create(owner=self.seller, trade_type='SELL', price_type='FIXED', fiat_currency=fiat, crypto_currency=crypto)
        snapshot = AdSnapshot.objects.create(ad=ad, trade_type='SELL', price_type='FIXED', fiat_currency=fiat, crypto_currency=crypto, appeal_cooldown_choice=60)
        self.order = Order.objects.create(owner=self.buyer, ad_snapshot=snapshot, arbiter=self.arbiter)
        Status.objects.bulk_create([Status(order=self.order, status='CNF')])
        OrderMember.objects.bulk_create([OrderMember(order=self.order, peer=self.buyer, type='BUYER')])

    def order_path(self):
        return f'/ws/ramp-p2p/subscribe/order/{self.order.pk}/'

    def general_path(self, user):
        return f'/ws/ramp-p2p/subscribe/general/{user.wallet_hash}/'

    async def open(self, path):
        socket = WebsocketCommunicator(URLRouter(websocket_urlpatterns), path)
        connected, _ = await socket.connect()
        self.assertTrue(connected)
        return socket

    async def authenticate(self, socket, user, token=None):
        await socket.send_json_to({'type': 'authenticate', 'wallet_hash': user.wallet_hash, 'token': token or self.tokens[user.wallet_hash]})

    def test_no_private_messages_or_presence_before_authentication(self):
        async def scenario():
            socket = await self.open(self.general_path(self.buyer))
            try:
                await get_channel_layer().group_send(general_room_name(self.buyer.wallet_hash), {'type': 'send_message', 'message': {'private': True}})
                self.assertTrue(await socket.receive_nothing(timeout=0.03))
                self.assertFalse(await database_sync_to_async(lambda: Peer.objects.get(pk=self.buyer.pk).is_online)())
            finally:
                await socket.disconnect()
        async_to_sync(scenario)()

    def test_order_stream_allows_only_buyer_seller_and_assigned_arbiter(self):
        async def scenario():
            for user in (self.buyer, self.seller, self.arbiter, self.outsider, self.other_arbiter):
                socket = await self.open(self.order_path())
                try:
                    await self.authenticate(socket, user)
                    if user in (self.outsider, self.other_arbiter):
                        self.assertEqual((await socket.receive_output())['type'], 'websocket.close')
                    else:
                        self.assertEqual((await socket.receive_json_from())['type'], 'ConnectionMessage')
                        await get_channel_layer().group_send(f'p2pxchange_order_{self.order.pk}', {'type': 'send_message', 'message': {'order': self.order.pk}})
                        self.assertEqual(await socket.receive_json_from(), {'order': self.order.pk})
                finally:
                    await socket.disconnect()
        async_to_sync(scenario)()

    def test_wrong_wallet_and_bad_token_cannot_change_presence(self):
        async def scenario():
            for user, token in ((self.outsider, None), (self.buyer, 'wrong-token')):
                socket = await self.open(self.general_path(self.buyer))
                try:
                    await self.authenticate(socket, user, token)
                    self.assertEqual((await socket.receive_output())['type'], 'websocket.close')
                finally:
                    await socket.disconnect()
            self.assertFalse(await database_sync_to_async(lambda: Peer.objects.get(pk=self.buyer.pk).is_online)())
        async_to_sync(scenario)()

    def test_general_authentication_updates_only_own_presence_and_receives_publisher_messages(self):
        async def scenario():
            socket = await self.open(self.general_path(self.buyer))
            try:
                await self.authenticate(socket, self.buyer)
                data = await socket.receive_json_from()
                self.assertEqual(data['extra']['unread_count'], 1)
                self.assertEqual(data['extra']['ongoing_count'], 1)
                self.assertTrue(await database_sync_to_async(lambda: Peer.objects.get(pk=self.buyer.pk).is_online)())
                self.assertFalse(await database_sync_to_async(lambda: Peer.objects.get(pk=self.seller.pk).is_online)())
                await database_sync_to_async(send_general_update)({'private': 'own'}, self.buyer.wallet_hash)
                self.assertEqual(await socket.receive_json_from(), {'private': 'own'})
            finally:
                await socket.disconnect()
        async_to_sync(scenario)()
        self.buyer.refresh_from_db()
        self.assertFalse(self.buyer.is_online)
        self.assertEqual(self.buyer.public_key, 'synthetic-key')

    def test_arbiter_presence_does_not_modify_peer_with_same_id(self):
        async def scenario():
            socket = await self.open(self.general_path(self.arbiter))
            try:
                await self.authenticate(socket, self.arbiter)
                data = await socket.receive_json_from()
                self.assertEqual(data['extra']['unread_count'], 0)
                self.assertEqual(data['extra']['ongoing_count'], 0)
                self.assertTrue(await database_sync_to_async(lambda: Arbiter.objects.get(pk=self.arbiter.pk).is_online)())
                self.assertFalse(await database_sync_to_async(lambda: Peer.objects.get(pk=self.buyer.pk).is_online)())
            finally:
                await socket.disconnect()
        async_to_sync(scenario)()

    def test_expired_disabled_and_rotated_credentials_are_rejected(self):
        async def scenario():
            for invalidation in ('expired', 'disabled', 'rotated'):
                if invalidation == 'expired':
                    await database_sync_to_async(AuthToken.objects.filter(wallet_hash=self.buyer.wallet_hash).update)(key_expires_at=timezone.now() - timedelta(seconds=1))
                elif invalidation == 'disabled':
                    await database_sync_to_async(AuthToken.objects.filter(wallet_hash=self.buyer.wallet_hash).update)(key_expires_at=timezone.now() + timedelta(hours=1))
                    await database_sync_to_async(Peer.objects.filter(pk=self.buyer.pk).update)(is_disabled=True)
                else:
                    await database_sync_to_async(Peer.objects.filter(pk=self.buyer.pk).update)(is_disabled=False)
                    await database_sync_to_async(AuthToken.objects.filter(wallet_hash=self.buyer.wallet_hash).update)(key=Fernet(settings.FERNET_KEY).encrypt(b'rotated-token').decode())
                socket = await self.open(self.order_path())
                try:
                    await self.authenticate(socket, self.buyer)
                    self.assertEqual((await socket.receive_output())['type'], 'websocket.close')
                finally:
                    await socket.disconnect()
        async_to_sync(scenario)()

    def test_removed_arbiter_assignment_blocks_delivery_on_existing_connection(self):
        async def scenario():
            socket = await self.open(self.order_path())
            try:
                await self.authenticate(socket, self.arbiter)
                await socket.receive_json_from()
                await database_sync_to_async(Order.objects.filter(pk=self.order.pk).update)(arbiter=None)
                await get_channel_layer().group_send(f'p2pxchange_order_{self.order.pk}', {'type': 'send_message', 'message': {'private': True}})
                self.assertEqual((await socket.receive_output())['type'], 'websocket.close')
            finally:
                await socket.disconnect()
        async_to_sync(scenario)()

    def test_disabling_account_blocks_delivery_on_existing_connection(self):
        async def scenario():
            socket = await self.open(self.general_path(self.buyer))
            try:
                await self.authenticate(socket, self.buyer)
                await socket.receive_json_from()
                await database_sync_to_async(Peer.objects.filter(pk=self.buyer.pk).update)(is_disabled=True)
                await database_sync_to_async(send_general_update)({'private': True}, self.buyer.wallet_hash)
                self.assertEqual((await socket.receive_output())['type'], 'websocket.close')
            finally:
                await socket.disconnect()
        async_to_sync(scenario)()

    def test_maintenance_blocks_private_authentication(self):
        FeatureControl.objects.create(name='P2P_MAINTENANCE', is_enabled=True)
        async def scenario():
            socket = await self.open(self.order_path())
            try:
                await self.authenticate(socket, self.buyer)
                self.assertEqual((await socket.receive_output())['type'], 'websocket.close')
            finally:
                await socket.disconnect()
        async_to_sync(scenario)()

    def test_missing_authentication_times_out_without_presence_update(self):
        async def scenario():
            with patch.object(PrivateUpdatesConsumer, 'authentication_timeout', 0.02):
                socket = await self.open(self.general_path(self.buyer))
                try:
                    output = await socket.receive_output()
                    self.assertEqual(output, {'type': 'websocket.close', 'code': 4401})
                finally:
                    await socket.disconnect()
        async_to_sync(scenario)()
        self.buyer.refresh_from_db()
        self.assertFalse(self.buyer.is_online)

    def test_malformed_authentication_frames_are_rejected(self):
        async def scenario():
            for data in ('not-json', '[]', '{}', '{"type":"authenticate","wallet_hash":1,"token":true}'):
                socket = await self.open(self.order_path())
                try:
                    await socket.send_to(text_data=data)
                    self.assertEqual((await socket.receive_output())['type'], 'websocket.close')
                finally:
                    await socket.disconnect()
        async_to_sync(scenario)()

    def test_missing_and_invalid_order_ids_are_rejected(self):
        async def scenario():
            for order_id in ('missing', '999999', '9' * 100):
                socket = await self.open(f'/ws/ramp-p2p/subscribe/order/{order_id}/')
                try:
                    await self.authenticate(socket, self.buyer)
                    self.assertEqual((await socket.receive_output())['type'], 'websocket.close')
                finally:
                    await socket.disconnect()
        async_to_sync(scenario)()

    def test_same_wallet_prefix_does_not_share_a_general_group(self):
        self.assertNotEqual(general_room_name('samehash-one'), general_room_name('samehash-two'))
        self.assertLessEqual(len(general_room_name('synthetic-wallet')), 100)

    def test_public_ad_and_market_streams_remain_available(self):
        async def scenario():
            for path in ('/ws/ramp-p2p/subscribe/ad/1/', '/ws/ramp-p2p/subscribe/market-price/USD/'):
                socket = await self.open(path)
                try:
                    self.assertEqual((await socket.receive_json_from())['type'], 'ConnectionMessage')
                finally:
                    await socket.disconnect()
        async_to_sync(scenario)()

    def test_same_prefix_wallets_cannot_receive_each_others_events(self):
        async def scenario():
            buyer = await self.open(self.general_path(self.buyer))
            outsider = await self.open(self.general_path(self.outsider))
            try:
                await self.authenticate(buyer, self.buyer)
                await self.authenticate(outsider, self.outsider)
                await buyer.receive_json_from()
                await outsider.receive_json_from()
                self.assertEqual(self.buyer.wallet_hash[:8], self.outsider.wallet_hash[:8])
                await database_sync_to_async(send_general_update)({'private': 'buyer'}, self.buyer.wallet_hash)
                self.assertEqual(await buyer.receive_json_from(), {'private': 'buyer'})
                self.assertTrue(await outsider.receive_nothing(timeout=0.03))
            finally:
                await buyer.disconnect()
                await outsider.disconnect()
        async_to_sync(scenario)()

    def test_expiry_rotation_and_maintenance_block_existing_streams(self):
        async def scenario():
            for invalidation in ('expiry', 'rotation', 'maintenance'):
                await database_sync_to_async(AuthToken.objects.filter(wallet_hash=self.buyer.wallet_hash).update)(
                    key=Fernet(settings.FERNET_KEY).encrypt(self.tokens[self.buyer.wallet_hash].encode()).decode(),
                    key_expires_at=timezone.now() + timedelta(hours=1),
                )
                socket = await self.open(self.order_path())
                try:
                    await self.authenticate(socket, self.buyer)
                    await socket.receive_json_from()
                    if invalidation == 'expiry':
                        await database_sync_to_async(AuthToken.objects.filter(wallet_hash=self.buyer.wallet_hash).update)(key_expires_at=timezone.now() - timedelta(seconds=1))
                    elif invalidation == 'rotation':
                        await database_sync_to_async(AuthToken.objects.filter(wallet_hash=self.buyer.wallet_hash).update)(key=Fernet(settings.FERNET_KEY).encrypt(b'new-token').decode())
                    else:
                        await database_sync_to_async(FeatureControl.objects.create)(name='P2P_MAINTENANCE', is_enabled=True)
                    await get_channel_layer().group_send(f'p2pxchange_order_{self.order.pk}', {'type': 'send_message', 'message': {'private': True}})
                    self.assertEqual((await socket.receive_output())['type'], 'websocket.close')
                finally:
                    await socket.disconnect()
        async_to_sync(scenario)()

    def test_retired_cash_in_websocket_route_is_absent(self):
        urlconf = type('Routes', (), {'urlpatterns': websocket_urlpatterns})
        with self.assertRaises(Resolver404):
            resolve('/ws/ramp-p2p/subscribe/synthetic_buyer/cash-in/', urlconf=urlconf)
