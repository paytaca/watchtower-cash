from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.signals import post_save
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from rampp2p.models import (
    Ad, AdSnapshot, Arbiter, CryptoCurrency, FiatCurrency, ImageUpload,
    Order, OrderPayment, OrderPaymentAttachment, PaymentMethod, PaymentType, Peer, Status,
)
from rampp2p.signals import on_order_update
from rampp2p.views.view_payment import OrderPaymentViewSet


class PaymentProofAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        def peer(pk, name):
            return Peer.objects.create(
                pk=pk, name=name, wallet_hash='synthetic-' + name,
                public_key='synthetic-key', address='synthetic-address',
            )

        cls.buyer = peer(1, 'buyer')
        cls.seller = peer(2, 'seller')
        cls.outsider = peer(3, 'outsider')
        # Deliberately overlap peer IDs to exercise typed authorization.
        cls.arbiter = Arbiter.objects.create(
            pk=1, name='assigned', wallet_hash='synthetic-assigned',
            public_key='synthetic-key', address='synthetic-address', is_disabled=False,
        )
        cls.other_arbiter = Arbiter.objects.create(
            pk=2, name='unassigned', wallet_hash='synthetic-unassigned',
            public_key='synthetic-key', address='synthetic-address', is_disabled=False,
        )
        fiat = FiatCurrency.objects.create(name='Synthetic fiat', symbol='TST')
        crypto = CryptoCurrency.objects.create(name='Synthetic BCH', symbol='TESTBCH')
        cls.payment_type = PaymentType.objects.create(full_name='Synthetic bank')
        cls.method = PaymentMethod.objects.create(owner=cls.seller, payment_type=cls.payment_type)
        cls.foreign_method = PaymentMethod.objects.create(owner=cls.outsider, payment_type=cls.payment_type)

        def payment(trade_type, foreign=False):
            ad_owner, creator = (cls.seller, cls.buyer) if trade_type == 'SELL' else (cls.buyer, cls.seller)
            if foreign:
                ad_owner = creator = cls.outsider
            with patch('rampp2p.signals.AdSummaryMessage.send_safe'):
                ad = Ad.objects.create(
                    owner=ad_owner, trade_type=trade_type, price_type='FIXED',
                    fiat_currency=fiat, crypto_currency=crypto,
                )
            snapshot = AdSnapshot.objects.create(
                ad=ad, trade_type=trade_type, price_type='FIXED',
                fiat_currency=fiat, crypto_currency=crypto, appeal_cooldown_choice=60,
            )
            order = Order.objects.create(owner=creator, ad_snapshot=snapshot, arbiter=cls.arbiter)
            Status.objects.bulk_create([Status(order=order, status='ESCRW')])
            return OrderPayment.objects.create(
                order=order, payment_method=cls.foreign_method if foreign else cls.method,
                payment_type=cls.payment_type,
            )

        cls.sell_payment = payment('SELL')
        cls.buy_payment = payment('BUY')
        cls.foreign_payment = payment('SELL', foreign=True)
        cls.image = ImageUpload.objects.create(
            url='https://example.invalid/synthetic-proof.png',
            url_path='/synthetic-proof.png', file_hash='synthetic-proof',
        )
        cls.attachment = OrderPaymentAttachment.objects.create(payment=cls.sell_payment, image=cls.image)

    def setUp(self):
        self.factory = APIRequestFactory()
        self.mocks = {}
        for name, target, value in (
            ('permission', 'authentication.permissions.RampP2PIsAuthenticated.has_permission', True),
            ('open', 'rampp2p.views.view_payment.open_image', Mock()),
            ('save', 'rampp2p.views.view_payment.file_upload_utils.save_image', self.image),
            ('delete', 'rampp2p.views.view_payment.file_upload_utils.delete_file', None),
        ):
            patcher = patch(target, return_value=value)
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)
        if post_save.disconnect(on_order_update, sender=Status):
            self.addCleanup(post_save.connect, on_order_update, sender=Status)

    def request(self, action, actor, method='get', pk=None, data=None, **headers):
        headers.setdefault('HTTP_WALLET_HASH', actor.wallet_hash)
        request = getattr(self.factory, method)('/unused/', data or {}, format='multipart', **headers)
        force_authenticate(request, user=actor)
        return OrderPaymentViewSet.as_view({method: action})(request, **({} if pk is None else {'pk': pk}))

    def upload(self, actor, payment, by_method=False, **headers):
        data = {'image': SimpleUploadedFile('proof.png', b'synthetic-image', content_type='image/png')}
        if by_method:
            data.update(order_id=payment.order_id, payment_method_id=payment.payment_method_id)
        return self.request(
            'upload_attachment_by_method' if by_method else 'upload_attachment', actor,
            method='post', pk=None if by_method else payment.pk, data=data, **headers,
        )

    def test_list_is_scoped_to_authenticated_participant(self):
        for actor, expected in (
            (self.buyer, {self.sell_payment.pk, self.buy_payment.pk}),
            (self.seller, {self.sell_payment.pk, self.buy_payment.pk}),
            (self.outsider, {self.foreign_payment.pk}),
            (self.arbiter, {self.sell_payment.pk, self.buy_payment.pk, self.foreign_payment.pk}),
            (self.other_arbiter, set()),
        ):
            with self.subTest(actor=actor.name):
                response = self.request('list', actor)
                self.assertEqual(response.status_code, 200)
                self.assertEqual({row['id'] for row in response.data}, expected)
        response = self.request('list', self.outsider, data={'order_id': self.sell_payment.order_id})
        self.assertEqual(response.data, [])

    def test_only_participants_can_retrieve_payment_and_nested_proofs(self):
        for payment in (self.sell_payment, self.buy_payment):
            for actor in (self.buyer, self.seller, self.arbiter):
                with self.subTest(payment=payment.pk, actor=actor.name):
                    self.assertEqual(self.request('retrieve', actor, pk=payment.pk).status_code, 200)
            for actor in (self.outsider, self.other_arbiter):
                self.assertEqual(self.request('retrieve', actor, pk=payment.pk).status_code, 403)
        response = self.request('retrieve', self.buyer, pk=self.sell_payment.pk)
        self.assertEqual(response.data['attachments'][0]['image']['url_path'], self.image.url_path)

    def test_headers_cannot_impersonate_a_participant(self):
        headers = {'HTTP_WALLET_HASH': self.buyer.wallet_hash}
        self.assertEqual(self.request('retrieve', self.outsider, pk=self.sell_payment.pk, **headers).status_code, 403)
        self.assertEqual(self.request('list', self.other_arbiter, **headers).data, [])
        for by_method in (False, True):
            self.assertEqual(self.upload(self.outsider, self.sell_payment, by_method, **headers).status_code, 403)
        self.mocks['open'].assert_not_called()
        self.mocks['save'].assert_not_called()

    def test_both_upload_routes_reject_every_non_buyer_before_file_or_database_writes(self):
        before = OrderPaymentAttachment.objects.count()
        for payment in (self.sell_payment, self.buy_payment):
            for actor in (self.seller, self.outsider, self.arbiter, self.other_arbiter):
                for by_method in (False, True):
                    with self.subTest(payment=payment.pk, actor=actor.name, by_method=by_method):
                        self.assertEqual(self.upload(actor, payment, by_method).status_code, 403)
        self.assertEqual(OrderPaymentAttachment.objects.count(), before)
        self.assertFalse(self.sell_payment.order.payment_methods.exists())
        self.mocks['open'].assert_not_called()
        self.mocks['save'].assert_not_called()

    def test_buyer_can_upload_via_both_routes_for_buy_and_sell_ads(self):
        for payment in (self.sell_payment, self.buy_payment):
            for by_method in (False, True):
                with self.subTest(payment=payment.pk, by_method=by_method):
                    response = self.upload(self.buyer, payment, by_method)
                    self.assertEqual(response.status_code, 201)
                    self.assertEqual(response.data['payment'], payment.pk)
                    self.assertTrue(OrderPaymentAttachment.objects.filter(payment=payment, image=self.image).exists())
        self.assertEqual(self.mocks['save'].call_count, 4)

    def test_by_method_creates_payment_only_for_buyer_and_seller_owned_method(self):
        method = PaymentMethod.objects.create(owner=self.seller, payment_type=self.payment_type)
        for actor, expected in ((self.seller, 403), (self.buyer, 201)):
            response = self.request('upload_attachment_by_method', actor, method='post', data={
                'order_id': self.buy_payment.order_id, 'payment_method_id': method.pk,
                'image': SimpleUploadedFile('proof.png', b'synthetic-image'),
            })
            self.assertEqual(response.status_code, expected)
            self.assertEqual(OrderPayment.objects.filter(order=self.buy_payment.order, payment_method=method).exists(), expected == 201)
        response = self.request('upload_attachment_by_method', self.buyer, method='post', data={
            'order_id': self.sell_payment.order_id, 'payment_method_id': self.foreign_method.pk,
            'image': SimpleUploadedFile('proof.png', b'synthetic-image'),
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(OrderPayment.objects.filter(order=self.sell_payment.order, payment_method=self.foreign_method).exists())

    def test_arbiter_wallet_collision_does_not_grant_buyer_access(self):
        Arbiter.objects.filter(pk=self.arbiter.pk).update(wallet_hash=self.buyer.wallet_hash)
        actor = Arbiter.objects.get(pk=self.arbiter.pk)
        for by_method in (False, True):
            self.assertEqual(self.upload(actor, self.sell_payment, by_method).status_code, 403)
        self.assertEqual(self.request('delete_attachment', actor, method='delete', pk=self.attachment.pk).status_code, 403)
        self.mocks['save'].assert_not_called()
        self.mocks['delete'].assert_not_called()

    def test_non_buyers_cannot_delete_proof_or_file(self):
        for actor in (self.seller, self.outsider, self.arbiter, self.other_arbiter):
            response = self.request('delete_attachment', actor, method='delete', pk=self.attachment.pk)
            self.assertEqual(response.status_code, 403)
        self.assertTrue(OrderPaymentAttachment.objects.filter(pk=self.attachment.pk).exists())
        self.mocks['delete'].assert_not_called()

    def test_buyer_can_delete_proof_for_buy_and_sell_ads(self):
        second = OrderPaymentAttachment.objects.create(payment=self.buy_payment, image=self.image)
        for attachment in (self.attachment, second):
            response = self.request('delete_attachment', self.buyer, method='delete', pk=attachment.pk)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(OrderPaymentAttachment.objects.filter(pk=attachment.pk).exists())
        self.mocks['delete'].assert_called_once_with(self.image.url_path)

    def test_deleting_one_proof_preserves_shared_file_and_other_attachment(self):
        other = OrderPaymentAttachment.objects.create(payment=self.foreign_payment, image=self.image)
        response = self.request('delete_attachment', self.buyer, method='delete', pk=self.attachment.pk)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(OrderPaymentAttachment.objects.filter(pk=other.pk).exists())
        self.mocks['delete'].assert_not_called()

    def test_finished_and_unfunded_orders_still_reject_proof_changes(self):
        for value in ('SBM', 'CNF', 'CNCL', 'RLS', 'RFN', 'PD'):
            Status.objects.filter(order=self.sell_payment.order).update(status=value)
            for by_method in (False, True):
                self.assertEqual(self.upload(self.buyer, self.sell_payment, by_method).status_code, 400)
            self.assertEqual(self.request('delete_attachment', self.buyer, method='delete', pk=self.attachment.pk).status_code, 400)
        self.mocks['save'].assert_not_called()
        self.mocks['delete'].assert_not_called()

    def test_paid_pending_orders_still_allow_buyer_uploads(self):
        Status.objects.filter(order=self.sell_payment.order).update(status='PD_PN')
        for by_method in (False, True):
            self.assertEqual(self.upload(self.buyer, self.sell_payment, by_method).status_code, 201)

    def test_removed_arbiter_assignment_revokes_reads(self):
        Order.objects.filter(pk=self.sell_payment.order_id).update(arbiter=None)
        self.assertEqual(self.request('retrieve', self.arbiter, pk=self.sell_payment.pk).status_code, 403)
        response = self.request('list', self.arbiter)
        self.assertNotIn(self.sell_payment.pk, {row['id'] for row in response.data})
