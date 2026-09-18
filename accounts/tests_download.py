from io import BytesIO

from django.contrib.auth.hashers import make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from accounts.download_store import (
    create_download_file,
    delete_download_file,
    get_download_file,
    sanitize_download_filename,
)
from accounts.models import DownloadFile
from kaixin.auth import SESSION_ADMIN_ID
from kaixin.store import create_admin_user


class DownloadFilenameTests(TestCase):
    def test_sanitize_strips_path_and_unsafe_chars(self):
        self.assertEqual(sanitize_download_filename('../../a b/report.pdf'), 'report.pdf')
        self.assertEqual(sanitize_download_filename(''), '')
        self.assertEqual(sanitize_download_filename('..'), '')


class DownloadEndpointTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_any_middle_path_downloads_by_filename(self):
        uploaded = SimpleUploadedFile(
            'notes.txt',
            b'hello download',
            content_type='text/plain',
        )
        row, error = create_download_file(uploaded)
        self.assertIsNone(error)
        for path in (
            f'/download/x/{row.filename}',
            f'/download/foo-bar/{row.filename}',
            f'/download/a/b/c/{row.filename}',
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn('attachment', response.get('Content-Disposition', ''))
            self.assertEqual(b''.join(response.streaming_content), b'hello download')

    def test_unknown_filename_redirects(self):
        from accounts.policy_store import update_blacklist_policy

        update_blacklist_policy({'download_redirect_url': 'https://miss.example/'})
        uploaded = SimpleUploadedFile('a.txt', b'x', content_type='text/plain')
        row, error = create_download_file(uploaded)
        self.assertIsNone(error)
        response = self.client.get('/download/x/other.txt')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://miss.example/')
        incomplete = self.client.get(
            '/download/adkjapdojciopqhjdpociqjcopiqijw/djfjoqjpoijpsaoidjcojadpajksdl'
        )
        self.assertEqual(incomplete.status_code, 302)
        self.assertEqual(incomplete.url, 'https://miss.example/')
        bare = self.client.get('/download/only-one-segment')
        self.assertEqual(bare.status_code, 302)
        self.assertEqual(bare.url, 'https://miss.example/')

    def test_duplicate_filename_rejected(self):
        first = SimpleUploadedFile('a.txt', b'1', content_type='text/plain')
        second = SimpleUploadedFile('copy.txt', b'2', content_type='text/plain')
        row, error = create_download_file(first, filename='same.txt')
        self.assertIsNone(error)
        row2, error2 = create_download_file(second, filename='same.txt')
        self.assertIsNone(row2)
        self.assertIn('already', error2.lower())

    def test_blacklisted_ip_can_still_download(self):
        from accounts.blacklist_store import KIND_LOGIN, add_blacklist_ip
        from accounts.policy_store import update_blacklist_policy

        update_blacklist_policy({'login_redirect_url': 'https://login.example/'})
        ip = '198.51.100.88'
        add_blacklist_ip(ip, KIND_LOGIN, note='test')
        uploaded = SimpleUploadedFile('ok.bin', b'data', content_type='application/octet-stream')
        row, error = create_download_file(uploaded)
        self.assertIsNone(error)
        response = self.client.get(
            f'/download/any-path/{row.filename}',
            REMOTE_ADDR=ip,
        )
        self.assertEqual(response.status_code, 200)

    def test_delete_removes_public_url(self):
        uploaded = SimpleUploadedFile('gone.txt', b'bye', content_type='text/plain')
        row, error = create_download_file(uploaded)
        self.assertIsNone(error)
        self.assertTrue(delete_download_file(str(row.id)))
        self.assertIsNone(get_download_file(row.filename, any_path='x'))
        from accounts.policy_store import update_blacklist_policy

        update_blacklist_policy({'download_redirect_url': 'https://gone.example/'})
        response = self.client.get(f'/download/x/{row.filename}')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://gone.example/')


class FilesAdminTests(TestCase):
    def setUp(self):
        admin = create_admin_user(
            'files-admin',
            make_password('pass'),
            is_superadmin=True,
            is_approved=True,
        )
        self.client = Client()
        session = self.client.session
        session[SESSION_ADMIN_ID] = admin['_id']
        session.save()

    def test_upload_lists_and_serves(self):
        page = self.client.get('/kaixin-judy-yuna/files/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Stored files')

        uploaded = SimpleUploadedFile(
            'admin-upload.pdf',
            BytesIO(b'%PDF-1.4 test').getvalue(),
            content_type='application/pdf',
        )
        saved = self.client.post(
            '/kaixin-judy-yuna/files/',
            {
                'action': 'upload',
                'file': uploaded,
                'filename': 'renamed.pdf',
            },
        )
        self.assertEqual(saved.status_code, 302)
        row = DownloadFile.objects.get()
        self.assertEqual(row.filename, 'renamed.pdf')

        listing = self.client.get('/kaixin-judy-yuna/files/')
        self.assertContains(listing, 'renamed.pdf')
        self.assertContains(listing, '/download/x/renamed.pdf')

        download = self.client.get('/download/custom/path/renamed.pdf')
        self.assertEqual(download.status_code, 200)

    def test_admin_can_set_miss_redirect(self):
        saved = self.client.post(
            '/kaixin-judy-yuna/files/',
            {
                'action': 'save_policy',
                'download_redirect_url': 'https://files-miss.example/',
            },
        )
        self.assertEqual(saved.status_code, 302)
        page = self.client.get('/kaixin-judy-yuna/files/')
        self.assertContains(page, 'https://files-miss.example/')
        response = self.client.get('/download/nope/missing.bin')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://files-miss.example/')
