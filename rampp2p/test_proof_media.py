from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image
from django.core.exceptions import ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIRequestFactory, force_authenticate

from rampp2p.models import Ad, AdSnapshot, Arbiter, CryptoCurrency, FiatCurrency, ImageUpload, Order, OrderPayment, OrderPaymentAttachment, PaymentMethod, PaymentType, Peer, Status
from rampp2p.serializers import ImageUploadSerializer
from rampp2p.utils.file_upload import save_image
from rampp2p.views.view_payment import OrderPaymentViewSet


class ProofStorageFixture:
    def configure_storage(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.media = self.root / 'media'
        self.legacy = self.media / 'image_uploads'
        self.private = self.root / 'private-proofs'
        self.legacy.mkdir(parents=True)
        setting = override_settings(
            MEDIA_ROOT=str(self.media), IMAGE_UPLOAD_ROOT=str(self.legacy),
            IMAGE_UPLOAD_FOLDER='image_uploads', IMAGE_UPLOAD_PATH='/media/image_uploads',
            P2P_PROOF_ROOT=str(self.private), ALLOWED_HOSTS=['testserver', 'another.test'],
        )
        setting.enable()
        self.addCleanup(setting.disable)


class ProofMediaAccessTests(ProofStorageFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        def peer(pk, name):
            return Peer.objects.create(pk=pk, name=name, wallet_hash='synthetic-' + name, public_key='synthetic-key', address='synthetic-address')
        cls.buyer = peer(1, 'buyer')
        cls.seller = peer(2, 'seller')
        cls.outsider = peer(3, 'outsider')
        cls.arbiter = Arbiter.objects.create(pk=1, name='assigned', wallet_hash='synthetic-arbiter', public_key='synthetic-key', address='synthetic-address', is_disabled=False)
        cls.other_arbiter = Arbiter.objects.create(pk=2, name='unassigned', wallet_hash='synthetic-other', public_key='synthetic-key', address='synthetic-address', is_disabled=False)
        fiat = FiatCurrency.objects.create(name='Synthetic fiat', symbol='TST')
        crypto = CryptoCurrency.objects.create(name='Synthetic BCH', symbol='TESTBCH')
        with patch('rampp2p.signals.AdSummaryMessage.send_safe'):
            ad = Ad.objects.create(owner=cls.seller, trade_type='SELL', price_type='FIXED', fiat_currency=fiat, crypto_currency=crypto)
        snapshot = AdSnapshot.objects.create(ad=ad, trade_type='SELL', price_type='FIXED', fiat_currency=fiat, crypto_currency=crypto, appeal_cooldown_choice=60)
        cls.order = Order.objects.create(owner=cls.buyer, ad_snapshot=snapshot, arbiter=cls.arbiter)
        Status.objects.bulk_create([Status(order=cls.order, status='ESCRW')])
        payment_type = PaymentType.objects.create(full_name='Synthetic bank')
        cls.method = PaymentMethod.objects.create(owner=cls.seller, payment_type=payment_type)
        cls.payment = OrderPayment.objects.create(order=cls.order, payment_method=cls.method, payment_type=payment_type)
        cls.image = ImageUpload.objects.create(url='https://example.invalid/media/image_uploads/proof.png', url_path='/media/image_uploads/proof.png', file_hash='synthetic-proof')
        cls.attachment = OrderPaymentAttachment.objects.create(payment=cls.payment, image=cls.image)

    def setUp(self):
        self.configure_storage()
        self.private.mkdir()
        (self.private / 'proof.png').write_bytes(b'synthetic-private-proof')
        self.factory = APIRequestFactory()
        patcher = patch('authentication.permissions.RampP2PIsAuthenticated.has_permission', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def request(self, actor=None, pk=None, **headers):
        request = self.factory.get('/unused/', **headers)
        if actor is not None:
            force_authenticate(request, user=actor)
        response = OrderPaymentViewSet.as_view({'get': 'retrieve_image'})(request, pk=self.image.pk if pk is None else pk)
        self.addCleanup(response.close)
        return response

    def test_buyer_seller_and_assigned_arbiter_can_read_image_with_private_cache_headers(self):
        for actor in (self.buyer, self.seller, self.arbiter):
            with self.subTest(actor=actor.name):
                response = self.request(actor)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b''.join(response.streaming_content), b'synthetic-private-proof')
                self.assertEqual(response['Cache-Control'], 'private, no-store')
                self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
                self.assertIn('Authorization', response['Vary'])

    def test_anonymous_unrelated_peers_and_arbiters_cannot_open_file(self):
        for actor, expected in ((None, 401), (self.outsider, 404), (self.other_arbiter, 404)):
            with self.subTest(actor=actor), patch('pathlib.Path.open') as open_file:
                self.assertEqual(self.request(actor).status_code, expected)
                open_file.assert_not_called()

    def test_header_cannot_override_authenticated_actor(self):
        with patch('pathlib.Path.open') as open_file:
            self.assertEqual(self.request(self.outsider, HTTP_WALLET_HASH=self.buyer.wallet_hash).status_code, 404)
            open_file.assert_not_called()

    def test_removed_arbiter_assignment_revokes_image_access(self):
        Order.objects.filter(pk=self.order.pk).update(arbiter=None)
        self.assertEqual(self.request(self.arbiter).status_code, 404)

    def test_orphan_and_missing_images_cannot_be_downloaded(self):
        OrderPaymentAttachment.objects.filter(pk=self.attachment.pk).delete()
        with patch('pathlib.Path.open') as open_file:
            self.assertEqual(self.request(self.buyer).status_code, 404)
            self.assertEqual(self.request(self.buyer, pk=999999).status_code, 404)
            open_file.assert_not_called()

    def test_buy_ad_participants_keep_image_access(self):
        AdSnapshot.objects.filter(pk=self.order.ad_snapshot_id).update(trade_type='BUY')
        for actor in (self.buyer, self.seller):
            self.assertEqual(self.request(actor).status_code, 200)

    def test_authorized_legacy_file_can_be_read_before_moving_storage(self):
        (self.private / 'proof.png').unlink()
        (self.legacy / 'proof.png').write_bytes(b'synthetic-legacy-proof')
        response = self.request(self.buyer)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'synthetic-legacy-proof')

    def test_malformed_paths_and_outside_symlinks_never_open_files(self):
        for path in ('/media/image_uploads/../outside.png', '/media/image_uploads/../../outside.png', '/media/other/proof.png'):
            ImageUpload.objects.filter(pk=self.image.pk).update(url_path=path)
            with patch('pathlib.Path.open') as open_file:
                self.assertEqual(self.request(self.buyer).status_code, 404)
                open_file.assert_not_called()
        ImageUpload.objects.filter(pk=self.image.pk).update(url_path='/media/image_uploads/proof.png')
        (self.private / 'proof.png').unlink()
        outside = self.root / 'outside.png'
        outside.write_bytes(b'synthetic-outside')
        (self.private / 'proof.png').symlink_to(outside)
        with patch('pathlib.Path.open') as open_file:
            self.assertEqual(self.request(self.buyer).status_code, 404)
            open_file.assert_not_called()

    def test_serialized_urls_reference_authenticated_endpoint_not_legacy_media(self):
        expected = reverse('order-payment-image', kwargs={'pk': self.image.pk})
        serialized = ImageUploadSerializer(self.image).data
        self.assertEqual(serialized['url'], expected)
        self.assertEqual(serialized['url_path'], expected)
        self.assertNotIn('/media/', serialized['url'])

    def test_new_upload_is_private_and_returns_authenticated_url(self):
        stream = BytesIO()
        Image.new('RGB', (2, 2), color='red').save(stream, 'PNG')
        request = self.factory.post('/unused/', {'image': SimpleUploadedFile('proof.png', stream.getvalue(), content_type='image/png')}, format='multipart')
        force_authenticate(request, user=self.buyer)
        response = OrderPaymentViewSet.as_view({'post': 'upload_attachment'})(request, pk=self.payment.pk)
        self.assertEqual(response.status_code, 201)
        new_image = ImageUpload.objects.get(pk=response.data['image']['id'])
        self.assertTrue((self.private / Path(new_image.url_path).name).is_file())
        self.assertFalse((self.legacy / Path(new_image.url_path).name).exists())
        self.assertEqual(response.data['image']['url_path'], reverse('order-payment-image', kwargs={'pk': new_image.pk}))
        self.assertEqual(self.request(self.buyer, pk=new_image.pk).status_code, 200)

    def test_duplicate_content_reuses_image_across_request_hosts(self):
        image = Image.new('RGB', (2, 2), color='blue')
        first = save_image(image, request=self.factory.get('/', HTTP_HOST='testserver'))
        second = save_image(image, request=self.factory.get('/', HTTP_HOST='another.test'))
        self.assertEqual(first.pk, second.pk)

    def test_buyer_deletion_removes_private_and_legacy_copies(self):
        (self.legacy / 'proof.png').write_bytes(b'synthetic-legacy-copy')
        request = self.factory.delete('/unused/')
        force_authenticate(request, user=self.buyer)
        response = OrderPaymentViewSet.as_view({'delete': 'delete_attachment'})(request, pk=self.attachment.pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse((self.private / 'proof.png').exists())
        self.assertFalse((self.legacy / 'proof.png').exists())


class ProofStorageMoveTests(ProofStorageFixture, SimpleTestCase):
    def setUp(self):
        self.configure_storage()
        (self.legacy / 'proof.png').write_bytes(b'synthetic-legacy-proof')

    def move(self, apply=False):
        output = StringIO()
        call_command('move_p2p_proofs_private', apply=apply, stdout=output)
        return output.getvalue()

    def test_dry_run_does_not_create_or_change_files(self):
        self.assertIn('DRY RUN', self.move())
        self.assertTrue((self.legacy / 'proof.png').exists())
        self.assertFalse(self.private.exists())

    def test_apply_moves_nested_proofs_without_touching_other_media_and_is_repeatable(self):
        (self.legacy / 'nested').mkdir()
        (self.legacy / 'nested' / 'other.png').write_bytes(b'synthetic-nested')
        (self.media / 'public.png').write_bytes(b'synthetic-public')
        self.move(apply=True)
        self.assertEqual((self.private / 'proof.png').read_bytes(), b'synthetic-legacy-proof')
        self.assertEqual((self.private / 'nested' / 'other.png').read_bytes(), b'synthetic-nested')
        self.assertFalse((self.legacy / 'proof.png').exists())
        self.assertTrue((self.media / 'public.png').exists())
        self.assertIn('Moved 0', self.move(apply=True))

    def test_conflicts_are_detected_before_any_file_moves(self):
        self.private.mkdir()
        (self.private / 'proof.png').write_bytes(b'different-content')
        (self.legacy / 'a-first.png').write_bytes(b'synthetic-first')
        with self.assertRaises(CommandError):
            self.move(apply=True)
        self.assertTrue((self.legacy / 'a-first.png').exists())
        self.assertEqual((self.private / 'proof.png').read_bytes(), b'different-content')

    def test_matching_private_copy_allows_removing_legacy_copy(self):
        self.private.mkdir()
        (self.private / 'proof.png').write_bytes(b'synthetic-legacy-proof')
        self.move(apply=True)
        self.assertFalse((self.legacy / 'proof.png').exists())
        self.assertEqual((self.private / 'proof.png').read_bytes(), b'synthetic-legacy-proof')

    def test_source_symlinks_are_rejected(self):
        (self.root / 'outside.png').write_bytes(b'synthetic-outside')
        (self.legacy / 'alias.png').symlink_to(self.root / 'outside.png')
        with self.assertRaises(CommandError):
            self.move(apply=True)
        self.assertTrue((self.legacy / 'proof.png').exists())

    def test_private_root_inside_public_media_or_static_is_rejected(self):
        for settings in ({'P2P_PROOF_ROOT': str(self.media / 'private')}, {'STATIC_ROOT': str(self.root), 'P2P_PROOF_ROOT': str(self.private)}):
            with override_settings(**settings), self.assertRaises(ImproperlyConfigured):
                self.move()
