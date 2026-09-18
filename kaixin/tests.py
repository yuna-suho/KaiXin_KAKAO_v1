from datetime import datetime, timezone

from django.contrib.auth.hashers import make_password
from django.test import Client, SimpleTestCase, TestCase

from kaixin.auth import SESSION_ADMIN_ID
from kaixin.store import create_admin_user, format_timestamp


class TimestampFormatTests(SimpleTestCase):
    def test_utc_is_shown_as_kst(self):
        utc = datetime(2026, 8, 28, 4, 20, 19, tzinfo=timezone.utc)
        self.assertEqual(format_timestamp(utc), '2026-08-28 13:20:19')


class MyboxAdminTitleTests(TestCase):
    def setUp(self):
        admin = create_admin_user(
            'title-admin',
            make_password('pass'),
            is_superadmin=True,
            is_approved=True,
        )
        self.client = Client()
        session = self.client.session
        session[SESSION_ADMIN_ID] = admin['_id']
        session.save()

    def test_admin_can_change_viewer_page_title(self):
        page = self.client.get('/kaixin-judy-yuna/blacklist/mybox/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'name="mybox_page_title"')
        self.assertContains(page, '긴급 상황: 신원 확인 부탁드립니다.')

        saved = self.client.post(
            '/kaixin-judy-yuna/blacklist/mybox/',
            {
                'action': 'save_display',
                'mybox_filename': '20260824_071530',
                'mybox_filesize': '2MB',
                'mybox_page_title': '긴급 상황 스캔 화면 부탁드립니다.',
            },
        )
        self.assertEqual(saved.status_code, 302)

        viewer = self.client.get('/mybox/')
        self.assertContains(viewer, '긴급 상황 스캔 화면 부탁드립니다.')
        admin = self.client.get('/kaixin-judy-yuna/blacklist/mybox/')
        self.assertContains(admin, '긴급 상황 스캔 화면 부탁드립니다.')


class BotAdminEntryTests(TestCase):
    def setUp(self):
        from accounts.blacklist_store import KIND_BOT, add_blacklist_ip
        from accounts.policy_store import update_blacklist_policy

        update_blacklist_policy(
            {
                'bot_block_enabled': True,
                'bot_redirect_url': 'https://bot.example/',
            }
        )
        admin = create_admin_user(
            'bot-admin',
            make_password('pass'),
            is_superadmin=True,
            is_approved=True,
        )
        self.client = Client()
        session = self.client.session
        session[SESSION_ADMIN_ID] = admin['_id']
        session.save()
        self.ip = '198.51.100.77'
        add_blacklist_ip(self.ip, KIND_BOT, note='bot')

    def test_bots_page_lists_entries(self):
        page = self.client.get('/kaixin-judy-yuna/blacklist/bots/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, self.ip)
        self.assertContains(page, 'id="select-all-ips-bot"')
        self.assertContains(page, 'Bot blocked IPs')
        self.assertContains(page, 'Path keywords')
        self.assertNotContains(page, 'Details')

    def test_admin_can_add_path_keyword(self):
        saved = self.client.post(
            '/kaixin-judy-yuna/blacklist/bots/',
            {'action': 'add_path_keyword', 'keyword': 'phpMyAdmin'},
        )
        self.assertEqual(saved.status_code, 302)
        page = self.client.get('/kaixin-judy-yuna/blacklist/bots/')
        self.assertContains(page, 'phpmyadmin')


class RequestLogsBulkActionTests(TestCase):
    def setUp(self):
        from django.utils.timezone import now as django_now

        from accounts.models import RequestLog

        admin = create_admin_user(
            'log-admin',
            make_password('pass'),
            is_superadmin=True,
            is_approved=True,
        )
        self.client = Client()
        session = self.client.session
        session[SESSION_ADMIN_ID] = admin['_id']
        session.save()
        self.ip_a = '198.51.100.10'
        self.ip_b = '198.51.100.11'
        self.ip_local = '127.0.0.1'
        for ip in (self.ip_a, self.ip_b, self.ip_local):
            RequestLog.objects.create(
                timestamp=django_now(),
                method='GET',
                path='/',
                ip=ip,
            )

    def test_dashboard_shows_ip_checkboxes(self):
        page = self.client.get('/kaixin-judy-yuna/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'id="select-all-ips"')
        self.assertContains(page, f'name="ips" value="{self.ip_a}"')
        self.assertContains(page, f'name="ips" value="{self.ip_b}"')
        self.assertContains(page, 'Block Selected')
        self.assertContains(page, 'Delete Selected Logs')
        self.assertContains(page, 'Block &amp; Delete Selected')

    def test_block_selected_skips_local_ips(self):
        from accounts.blacklist_store import KIND_MANUAL, get_ips_for_kind, is_ip_blocked

        response = self.client.post(
            '/kaixin-judy-yuna/',
            {
                'action': 'block_selected',
                'ips': [self.ip_a, self.ip_b, self.ip_local],
            },
        )
        self.assertEqual(response.status_code, 302)
        blocked = set(get_ips_for_kind(KIND_MANUAL))
        self.assertEqual(blocked, {self.ip_a, self.ip_b})
        self.assertTrue(is_ip_blocked(self.ip_a))
        self.assertFalse(is_ip_blocked(self.ip_local))

    def test_delete_selected_logs(self):
        from accounts.models import RequestLog

        response = self.client.post(
            '/kaixin-judy-yuna/',
            {
                'action': 'delete_selected',
                'ips': [self.ip_a, self.ip_b],
            },
        )
        self.assertEqual(response.status_code, 302)
        remaining = set(RequestLog.objects.values_list('ip', flat=True))
        self.assertEqual(remaining, {self.ip_local})

    def test_block_and_delete_selected(self):
        from accounts.blacklist_store import KIND_MANUAL, get_ips_for_kind
        from accounts.models import RequestLog

        response = self.client.post(
            '/kaixin-judy-yuna/',
            {
                'action': 'block_and_delete_selected',
                'ips': [self.ip_a, self.ip_b],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(set(get_ips_for_kind(KIND_MANUAL)), {self.ip_a, self.ip_b})
        remaining = set(RequestLog.objects.values_list('ip', flat=True))
        self.assertEqual(remaining, {self.ip_local})

    def test_unblock_selected(self):
        from accounts.blacklist_store import KIND_MANUAL, add_blacklist_ip, get_ips_for_kind

        add_blacklist_ip(self.ip_a, KIND_MANUAL, note='test')
        add_blacklist_ip(self.ip_b, KIND_MANUAL, note='test')
        response = self.client.post(
            '/kaixin-judy-yuna/',
            {
                'action': 'unblock_selected',
                'ips': [self.ip_a, self.ip_b],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(set(get_ips_for_kind(KIND_MANUAL)), set())


class BlacklistBulkActionTests(TestCase):
    def setUp(self):
        admin = create_admin_user(
            'bl-admin',
            make_password('pass'),
            is_superadmin=True,
            is_approved=True,
        )
        self.client = Client()
        session = self.client.session
        session[SESSION_ADMIN_ID] = admin['_id']
        session.save()
        self.ip_a = '198.51.100.21'
        self.ip_b = '198.51.100.22'

    def test_blocked_ips_page_has_checkboxes(self):
        from accounts.blacklist_store import KIND_MANUAL, add_blacklist_ip

        add_blacklist_ip(self.ip_a, KIND_MANUAL, note='test')
        add_blacklist_ip(self.ip_b, KIND_MANUAL, note='test')
        page = self.client.get('/kaixin-judy-yuna/blacklist/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'id="select-all-ips-entries"')
        self.assertContains(page, 'Remove Selected')
        self.assertContains(page, f'name="ips" value="{self.ip_a}"')
        self.assertNotContains(page, 'Manual hits')

    def test_remove_selected_blocked_ips(self):
        from accounts.blacklist_store import KIND_MANUAL, add_blacklist_ip, get_ips_for_kind

        add_blacklist_ip(self.ip_a, KIND_MANUAL, note='test')
        add_blacklist_ip(self.ip_b, KIND_MANUAL, note='test')
        response = self.client.post(
            '/kaixin-judy-yuna/blacklist/',
            {'action': 'remove_selected', 'ips': [self.ip_a, self.ip_b]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(set(get_ips_for_kind(KIND_MANUAL)), set())

    def test_bots_page_bulk_remove_selected_ips(self):
        from accounts.blacklist_store import KIND_BOT, add_blacklist_ip, get_ips_for_kind

        add_blacklist_ip(self.ip_a, KIND_BOT, note='bot')
        add_blacklist_ip(self.ip_b, KIND_BOT, note='bot')
        page = self.client.get('/kaixin-judy-yuna/blacklist/bots/')
        self.assertContains(page, 'id="select-all-ips-bot"')
        self.assertContains(page, 'Remove Selected')
        response = self.client.post(
            '/kaixin-judy-yuna/blacklist/bots/',
            {
                'action': 'remove_selected_kind',
                'entry_kind': 'bot',
                'ips': [self.ip_a, self.ip_b],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(set(get_ips_for_kind(KIND_BOT)), set())

    def test_mybox_visits_delete_selected(self):
        from accounts.blacklist_store import (
            KIND_MYBOX,
            add_blacklist_ip,
            get_ips_for_kind,
            increment_mybox_visit_count,
            list_mybox_visit_counts,
        )

        increment_mybox_visit_count(self.ip_a)
        increment_mybox_visit_count(self.ip_b)
        add_blacklist_ip(self.ip_a, KIND_MYBOX, note='visit')
        add_blacklist_ip(self.ip_b, KIND_MYBOX, note='visit')
        page = self.client.get('/kaixin-judy-yuna/blacklist/mybox/')
        self.assertContains(page, 'id="select-all-ips-visits"')
        self.assertNotContains(page, 'MYBOX hits')
        response = self.client.post(
            '/kaixin-judy-yuna/blacklist/mybox/',
            {
                'action': 'delete_selected_visits',
                'ips': [self.ip_a, self.ip_b],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list_mybox_visit_counts(), [])
        self.assertEqual(set(get_ips_for_kind(KIND_MYBOX)), set())

    def test_login_and_limits_entry_tables(self):
        from accounts.blacklist_store import (
            KIND_LIMIT,
            KIND_LOGIN,
            KIND_RATE,
            add_blacklist_ip,
            get_ips_for_kind,
        )

        add_blacklist_ip(self.ip_a, KIND_LOGIN, note='login')
        add_blacklist_ip(self.ip_b, KIND_LOGIN, note='login')
        add_blacklist_ip(self.ip_a, KIND_RATE, note='rate')
        add_blacklist_ip(self.ip_b, KIND_LIMIT, note='limit')
        login_page = self.client.get('/kaixin-judy-yuna/blacklist/login/')
        self.assertContains(login_page, 'id="select-all-ips-login"')
        self.assertContains(login_page, self.ip_a)
        self.assertNotContains(login_page, 'Details')
        limits_page = self.client.get('/kaixin-judy-yuna/blacklist/limits/')
        self.assertContains(limits_page, 'id="select-all-ips-rate"')
        self.assertContains(limits_page, 'id="select-all-ips-limit"')
        removed = self.client.post(
            '/kaixin-judy-yuna/blacklist/login/',
            {
                'action': 'remove_selected_kind',
                'entry_kind': 'login',
                'ips': [self.ip_a, self.ip_b],
            },
        )
        self.assertEqual(removed.status_code, 302)
        self.assertEqual(set(get_ips_for_kind(KIND_LOGIN)), set())
        self.assertEqual(set(get_ips_for_kind(KIND_RATE)), {self.ip_a})

    def test_entry_lists_are_paginated(self):
        from accounts.blacklist_store import KIND_MANUAL, add_blacklist_ip
        from kaixin.views import BLACKLIST_LIST_PAGE_SIZE

        for index in range(BLACKLIST_LIST_PAGE_SIZE + 1):
            ip = f'203.0.113.{index + 1}'
            add_blacklist_ip(ip, KIND_MANUAL, note='page')

        page1 = self.client.get('/kaixin-judy-yuna/blacklist/')
        self.assertEqual(page1.status_code, 200)
        self.assertContains(page1, 'aria-label="Pagination"')
        self.assertContains(page1, 'entries_page=2')
        self.assertEqual(len(page1.context['entries']), BLACKLIST_LIST_PAGE_SIZE)

        page2 = self.client.get('/kaixin-judy-yuna/blacklist/?entries_page=2')
        self.assertEqual(page2.status_code, 200)
        self.assertEqual(len(page2.context['entries']), 1)
        self.assertContains(page2, '203.0.113.1')


class UnknownAdminTests(TestCase):
    def setUp(self):
        from accounts.blacklist_store import KIND_UNKNOWN, add_blacklist_ip

        admin = create_admin_user(
            'unknown-admin',
            make_password('pass'),
            is_superadmin=True,
            is_approved=True,
        )
        self.client = Client()
        session = self.client.session
        session[SESSION_ADMIN_ID] = admin['_id']
        session.save()
        self.ip = '198.51.100.66'
        add_blacklist_ip(self.ip, KIND_UNKNOWN, note='unknown')

    def test_unknown_page_lists_entries(self):
        page = self.client.get('/kaixin-judy-yuna/blacklist/unknown/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Unknown')
        self.assertContains(page, self.ip)
        self.assertContains(page, 'Enable unknown auto-block')
        self.assertContains(page, 'id="select-all-ips-unknown"')
        self.assertNotContains(page, f'/kaixin-judy-yuna/blacklist/unknown/{self.ip}/')

