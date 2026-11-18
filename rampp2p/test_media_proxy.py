from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from rampp2p.views.view_utils import media_proxy_view


class MediaProxyTests(SimpleTestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.media = self.root / 'media'
        self.media.mkdir()
        (self.media / 'uploads').mkdir()
        (self.media / 'uploads' / 'receipt.png').write_bytes(b'synthetic-image')
        (self.root / 'outside.txt').write_bytes(b'synthetic-private-marker')
        sibling = self.root / 'media-private'
        sibling.mkdir()
        (sibling / 'marker.txt').write_bytes(b'synthetic-sibling-marker')
        override = override_settings(MEDIA_ROOT=str(self.media))
        override.enable()
        self.addCleanup(override.disable)
        self.request = RequestFactory().get('/media/uploads/receipt.png')

    def response(self, path):
        response = media_proxy_view(self.request, path=path)
        self.addCleanup(response.close)
        return response

    def assert_not_found(self, path):
        # Resolving metadata is allowed; rejected paths must not open any file.
        with patch('pathlib.Path.open') as open_file:
            self.assertEqual(self.response(path).status_code, 404)
            open_file.assert_not_called()

    def test_nested_media_file_is_served(self):
        response = self.response('uploads/receipt.png')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'synthetic-image')

    def test_traversal_and_sibling_prefix_escape_are_rejected(self):
        for path in ('../outside.txt', 'uploads/../../outside.txt', '../media-private/marker.txt'):
            with self.subTest(path=path):
                self.assert_not_found(path)

    def test_absolute_paths_are_rejected_even_inside_media(self):
        for path in (str(self.root / 'outside.txt'), str(self.media / 'uploads/receipt.png')):
            with self.subTest(path=path):
                self.assert_not_found(path)

    def test_file_symlink_outside_media_is_rejected(self):
        (self.media / 'escape.txt').symlink_to(self.root / 'outside.txt')
        self.assert_not_found('escape.txt')

    def test_directory_symlink_outside_media_is_rejected(self):
        (self.media / 'escape').symlink_to(self.root / 'media-private', target_is_directory=True)
        self.assert_not_found('escape/marker.txt')

    def test_symlink_inside_media_is_served(self):
        (self.media / 'receipt.png').symlink_to(self.media / 'uploads/receipt.png')
        response = self.response('receipt.png')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'synthetic-image')

    def test_missing_files_directories_and_invalid_paths_return_404(self):
        (self.media / 'broken').symlink_to(self.root / 'missing.txt')
        (self.media / 'loop').symlink_to(self.media / 'loop')
        for path in ('', 'uploads', 'missing.png', 'broken', 'loop', 'bad\x00name'):
            with self.subTest(path=path):
                self.assert_not_found(path)

    def test_missing_media_root_returns_404(self):
        with override_settings(MEDIA_ROOT=str(self.root / 'missing-directory')):
            self.assert_not_found('receipt.png')

    def test_unreadable_file_returns_404(self):
        with patch('pathlib.Path.open', side_effect=PermissionError):
            self.assertEqual(self.response('uploads/receipt.png').status_code, 404)

    def test_media_root_can_itself_be_a_symlink(self):
        alias = self.root / 'media-alias'
        alias.symlink_to(self.media, target_is_directory=True)
        with override_settings(MEDIA_ROOT=str(alias)):
            response = self.response('uploads/receipt.png')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'synthetic-image')
