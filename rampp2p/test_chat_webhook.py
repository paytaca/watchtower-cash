import base64
import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import bitcoin
import ecdsa
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from rampp2p.models import Ad, AdSnapshot, Appeal, Arbiter, ChatWebhookDelivery, CryptoCurrency, FiatCurrency, Order, Peer
from rampp2p.views.view_webhooks import ChatWebhookView


class ChatWebhookTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        def peer(name, chat_id):
            return Peer.objects.create(name=name, wallet_hash='synthetic-' + name, public_key='synthetic-key', address='synthetic-address', chat_identity_id=chat_id)
        cls.buyer = peer('buyer', 101)
        cls.seller = peer('seller', 202)
        cls.outsider = peer('outsider', 303)
        cls.arbiter = Arbiter.objects.create(name='assigned', wallet_hash='synthetic-arbiter', public_key='synthetic-key', address='synthetic-address', chat_identity_id=404, is_disabled=False)
        fiat = FiatCurrency.objects.create(name='Synthetic fiat', symbol='TST')
        crypto = CryptoCurrency.objects.create(name='Synthetic BCH', symbol='TESTBCH')
        with patch('rampp2p.signals.AdSummaryMessage.send_safe'):
            cls.ad = Ad.objects.create(owner=cls.seller, trade_type='SELL', price_type='FIXED', fiat_currency=fiat, crypto_currency=crypto)
        snapshot = AdSnapshot.objects.create(ad=cls.ad, trade_type='SELL', price_type='FIXED', fiat_currency=fiat, crypto_currency=crypto, appeal_cooldown_choice=60)
        cls.order = Order.objects.create(owner=cls.buyer, ad_snapshot=snapshot, chat_session_ref='synthetic-session', arbiter=cls.arbiter)

    def setUp(self):
        self.factory = APIRequestFactory()
        self.private_key = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1).to_string().hex()
        self.public_key = bitcoin.privtopub(self.private_key)
        setting = override_settings(P2P_CHAT_WEBHOOK_PUBLIC_KEY=self.public_key)
        setting.enable()
        self.addCleanup(setting.disable)
        patcher = patch('rampp2p.signals.AppealSummaryMessage.send_safe')
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch('rampp2p.views.view_webhooks.send_push_notification')
        self.push = patcher.start()
        self.addCleanup(patcher.stop)

    def payload(self, **changes):
        data = {
            'id': 123, 'chat_session_ref': self.order.chat_session_ref,
            'created_at': timezone.now().isoformat(),
            'chat_identity': {'id': self.buyer.chat_identity_id, 'name': 'synthetic'},
            'message': 'synthetic encrypted message', 'encrypted': True,
        }
        data.update(changes)
        return data

    def request(self, data=None, body=None, signature=None, private_key=None, **headers):
        if body is None:
            body = json.dumps(self.payload() if data is None else data)
        if signature is None:
            signature = bitcoin.ecdsa_sign(body, private_key or self.private_key)
        headers.setdefault('HTTP_X_CHAT_WEBHOOK_EVENT', 'new-message')
        headers['HTTP_X_CHAT_WEBHOOK_SIGNATURE'] = signature
        request = self.factory.generic('POST', '/chats/webhook/', body, content_type='application/json', **headers)
        return ChatWebhookView.as_view()(request)

    def test_existing_chat_service_signature_format_notifies_counterparty(self):
        self.assertEqual(self.request().status_code, 200)
        self.push.assert_called_once_with([self.seller.wallet_hash], f'New message from Order No. {self.order.pk}', extra={'type': 'new_message', 'order_id': self.order.pk})
        self.assertTrue(ChatWebhookDelivery.objects.filter(message_id=123).exists())

    def test_seller_sender_notifies_buyer_for_both_trade_directions(self):
        for trade_type, message_id in (('SELL', 123), ('BUY', 124)):
            AdSnapshot.objects.filter(pk=self.order.ad_snapshot_id).update(trade_type=trade_type)
            response = self.request(self.payload(id=message_id, chat_identity={'id': self.seller.chat_identity_id}))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.push.call_args.args[0], [self.buyer.wallet_hash])

    def test_compressed_wif_sender_key_is_compatible(self):
        private_key = bitcoin.encode_privkey(self.private_key, 'wif_compressed')
        with override_settings(P2P_CHAT_WEBHOOK_PUBLIC_KEY=bitcoin.privtopub(private_key)):
            self.assertEqual(self.request(private_key=private_key).status_code, 200)

    def test_unsigned_malformed_and_wrong_signer_requests_are_rejected_before_queries(self):
        wrong_key = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1).to_string().hex()
        for signature in ('', 'not-base64', base64.b64encode(b'\0' * 65).decode()):
            with self.subTest(signature=signature), self.assertNumQueries(0):
                self.assertEqual(self.request(signature=signature).status_code, 403)
        with self.assertNumQueries(0):
            self.assertEqual(self.request(private_key=wrong_key).status_code, 403)
        self.push.assert_not_called()
        self.assertFalse(ChatWebhookDelivery.objects.exists())

    def test_unconfigured_or_invalid_pinned_key_fails_closed(self):
        for key in ('', None, 'not-a-key', 'ff' * 33):
            with override_settings(P2P_CHAT_WEBHOOK_PUBLIC_KEY=key), self.assertNumQueries(0):
                self.assertEqual(self.request().status_code, 503)
        self.push.assert_not_called()

    def test_modified_body_or_reserialized_json_cannot_reuse_signature(self):
        data = self.payload()
        original = json.dumps(data)
        signature = bitcoin.ecdsa_sign(original, self.private_key)
        for body in (json.dumps({**data, 'chat_session_ref': 'another-session'}), json.dumps(data, separators=(',', ':'))):
            with self.assertNumQueries(0):
                self.assertEqual(self.request(body=body, signature=signature).status_code, 403)
        self.push.assert_not_called()

    def test_caller_supplied_public_key_cannot_replace_pinned_sender_key(self):
        wrong_key = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1).to_string().hex()
        self.assertEqual(self.request(private_key=wrong_key, HTTP_PUBLIC_KEY=bitcoin.privtopub(wrong_key)).status_code, 403)
        self.push.assert_not_called()

    def test_duplicate_delivery_returns_success_without_repeated_notifications(self):
        data = self.payload()
        for _ in range(3):
            self.assertEqual(self.request(data).status_code, 200)
        self.push.assert_called_once()
        self.assertEqual(ChatWebhookDelivery.objects.count(), 1)

    def test_stale_and_future_signed_messages_are_rejected(self):
        for date in (timezone.now() - timedelta(days=2), timezone.now() + timedelta(minutes=10)):
            self.assertEqual(self.request(self.payload(created_at=date.isoformat())).status_code, 403)
        self.push.assert_not_called()
        self.assertFalse(ChatWebhookDelivery.objects.exists())

    def test_signed_malformed_payloads_return_validation_errors(self):
        data = self.payload()
        malformed = [[], {}, {**data, 'id': 0}, {**data, 'id': 2**64}, {**data, 'chat_identity': None}, {**data, 'chat_identity': {}}, {**data, 'created_at': 'invalid'}, {**data, 'chat_session_ref': ''}]
        for item in malformed:
            with self.subTest(item=item):
                self.assertEqual(self.request(item).status_code, 400)
        self.push.assert_not_called()
        self.assertFalse(ChatWebhookDelivery.objects.exists())

    def test_unsupported_event_is_rejected_without_notifications(self):
        self.assertEqual(self.request(HTTP_X_CHAT_WEBHOOK_EVENT='other-event').status_code, 400)
        self.push.assert_not_called()

    def test_pruning_receipt_does_not_make_old_signed_message_replayable(self):
        data = self.payload()
        self.assertEqual(self.request(data).status_code, 200)
        future = timezone.now() + timedelta(days=2)
        with patch('rampp2p.views.view_webhooks.timezone.now', return_value=future):
            call_command('prune_p2p_chat_webhooks', stdout=StringIO())
            self.assertFalse(ChatWebhookDelivery.objects.exists())
            self.assertEqual(self.request(data).status_code, 403)
        self.push.assert_called_once()

    def test_unrelated_or_unknown_chat_identity_cannot_trigger_notifications(self):
        for identity_id in (self.outsider.chat_identity_id, 999999):
            self.assertEqual(self.request(self.payload(chat_identity={'id': identity_id})).status_code, 403)
        self.push.assert_not_called()
        self.assertFalse(ChatWebhookDelivery.objects.exists())

    def test_ambiguous_participant_identity_mapping_is_rejected(self):
        Peer.objects.filter(pk=self.seller.pk).update(chat_identity_id=self.buyer.chat_identity_id)
        self.assertEqual(self.request().status_code, 403)
        self.push.assert_not_called()

    def test_missing_or_ambiguous_chat_session_is_rejected(self):
        self.assertEqual(self.request(self.payload(chat_session_ref='missing')).status_code, 404)
        Order.objects.create(owner=self.outsider, ad_snapshot=self.order.ad_snapshot, chat_session_ref=self.order.chat_session_ref)
        self.assertEqual(self.request().status_code, 400)
        self.push.assert_not_called()

    def test_peer_appeal_message_notifies_counterparty_and_assigned_arbiter(self):
        appeal = Appeal.objects.create(order=self.order, owner=self.buyer, type='RLS')
        self.assertEqual(self.request().status_code, 200)
        self.assertEqual(self.push.call_count, 2)
        self.assertEqual(self.push.call_args_list[0].args[0], [self.arbiter.wallet_hash])
        self.assertEqual(self.push.call_args_list[1].args[0], [self.seller.wallet_hash])
        self.assertEqual(self.push.call_args.kwargs['extra']['appeal_id'], appeal.pk)

    def test_arbiter_can_notify_both_peers_only_for_assigned_appeal(self):
        data = self.payload(chat_identity={'id': self.arbiter.chat_identity_id})
        self.assertEqual(self.request(data).status_code, 403)
        Appeal.objects.create(order=self.order, owner=self.buyer, type='RLS')
        self.assertEqual(self.request(data).status_code, 200)
        self.push.assert_called_once()
        self.assertEqual(set(self.push.call_args.args[0]), {self.buyer.wallet_hash, self.seller.wallet_hash})

    def test_unassigned_arbiter_cannot_trigger_appeal_notifications(self):
        Appeal.objects.create(order=self.order, owner=self.buyer, type='RLS')
        other = Arbiter.objects.create(name='unassigned', wallet_hash='synthetic-other', public_key='synthetic-key', address='synthetic-address', chat_identity_id=505)
        self.assertEqual(self.request(self.payload(chat_identity={'id': other.chat_identity_id})).status_code, 403)
        self.push.assert_not_called()

    def test_failed_push_rolls_back_replay_claim_so_sender_can_retry(self):
        data = self.payload()
        self.push.side_effect = RuntimeError('synthetic delivery failure')
        with self.assertRaises(RuntimeError):
            self.request(data)
        self.assertFalse(ChatWebhookDelivery.objects.exists())
        self.push.side_effect = None
        self.assertEqual(self.request(data).status_code, 200)
        self.assertTrue(ChatWebhookDelivery.objects.exists())

    def test_cleanup_only_removes_expired_replay_records_in_bounded_batches(self):
        old = timezone.now() - timedelta(days=1)
        ChatWebhookDelivery.objects.bulk_create([
            ChatWebhookDelivery(message_id=1, expires_at=old),
            ChatWebhookDelivery(message_id=2, expires_at=old),
            ChatWebhookDelivery(message_id=3, expires_at=timezone.now() + timedelta(hours=1)),
        ])
        call_command('prune_p2p_chat_webhooks', batch_size=1, stdout=StringIO())
        self.assertEqual(ChatWebhookDelivery.objects.filter(expires_at=old).count(), 1)
        self.assertTrue(ChatWebhookDelivery.objects.filter(pk=3).exists())
