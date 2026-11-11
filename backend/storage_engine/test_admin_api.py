import io
import logging
from datetime import timedelta
from contextlib import redirect_stdout
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from rest_framework.test import APIClient
from telethon import errors as te

from authentication.models import ApiToken
from drive.models import StorageSettings
from storage_engine import alerts, credentials, health
from storage_engine.fakes import REAL_RESOLVE, StorageTestCase
from storage_engine.secrets import decrypt
from storage_engine.selftest import run_selftest

User = get_user_model()
BASE = '/api/admin/storage/'
WEBHOOK = 'https://ntfy.example.com/my-topic'
def make_valid_session_string():
    """A syntactically valid Telethon StringSession with a dummy auth key (never contacts Telegram)."""
    from telethon.crypto import AuthKey
    from telethon.sessions import StringSession
    session = StringSession()
    session.set_dc(2, '149.154.167.51', 443)
    session.auth_key = AuthKey(b'\x01' * 256)
    return session.save()


VALID_SESSION = make_valid_session_string()
CODE = '48151'
PASSWORD = 'correct horse battery staple'


class AdminTestCase(StorageTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(email='admin@example.com', password='Password123!', is_superuser=True)
        self.client = APIClient(raise_request_exception=False)
        self.client.force_authenticate(user=self.admin)

    def row(self):
        return StorageSettings.objects.get(pk=1)


class AdminPermissionTests(AdminTestCase):
    ROUTES = [
        ('get', ''), ('put', ''), ('post', 'test/'), ('post', 'test-alert/'), ('post', 'selftest/'),
        ('post', 'login/start/'), ('post', 'login/verify/'), ('post', 'login/password/'), ('post', 'login/cancel/'),
    ]

    def test_anonymous_is_401(self):
        for method, path in self.ROUTES:
            with self.subTest(path=path):
                self.assertEqual(getattr(APIClient(), method)(BASE + path).status_code, 401)

    def test_non_superuser_is_403(self):
        user = User.objects.create_user(email='user@example.com', password='Password123!')
        client = APIClient()
        client.force_authenticate(user=user)
        for method, path in self.ROUTES:
            with self.subTest(path=path):
                self.assertEqual(getattr(client, method)(BASE + path).status_code, 403)

    def test_api_token_is_403_even_for_a_superuser_owner(self):
        plaintext = ApiToken.generate_plaintext()
        ApiToken.objects.create(user=self.admin, name='t', prefix=plaintext[:12], scopes=['read', 'files:upload'],
                                token_hash=ApiToken.hash_token(plaintext))
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {plaintext}')
        for method, path in self.ROUTES:
            with self.subTest(path=path):
                self.assertEqual(getattr(client, method)(BASE + path).status_code, 403)

    def test_me_exposes_is_superuser_read_only(self):
        self.assertTrue(self.client.get('/api/auth/me/').json()['is_superuser'])


class AdminSettingsTests(AdminTestCase):
    def test_get_defaults_has_no_secrets(self):
        body = self.client.get(BASE).json()
        self.assertEqual((body['has_session'], body['effective_source'], body['credentials_unreadable']),
                         (False, 'env', False))
        self.assertNotIn('session_string', body)
        self.assertNotIn('session_string_enc', body)

    def test_put_updates_fields_and_never_returns_the_session(self):
        res = self.client.put(BASE, {
            'chat_id': '-100123', 'alert_format': 'discord', 'alert_webhook_url': WEBHOOK,
            'alert_telegram_chat_id': '42', 'alert_min_interval_minutes': 60,
        }, format='json')
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual((body['chat_id'], body['alert_format'], body['alert_min_interval_minutes']),
                         ('-100123', 'discord', 60))
        self.assertTrue(body['alert_webhook_set'])
        self.assertEqual(body['alert_webhook_host'], 'ntfy.example.com')
        self.assertNotIn('my-topic', res.content.decode())
        self.assertEqual(self.row().updated_by, self.admin)

    def test_session_string_semantics_replace_keep_clear(self):
        self.assertEqual(self.client.put(BASE, {'session_string': VALID_SESSION}, format='json').status_code, 200)
        self.assertEqual(decrypt(self.row().session_string_enc), VALID_SESSION)
        self.assertTrue(self.client.get(BASE).json()['has_session'])
        self.assertEqual(self.client.get(BASE).json()['effective_source'], 'db')

        # omitted keeps
        self.client.put(BASE, {'chat_id': '@mychannel'}, format='json')
        self.assertEqual(decrypt(self.row().session_string_enc), VALID_SESSION)
        # blank keeps (an untouched password-style input)
        self.client.put(BASE, {'session_string': ''}, format='json')
        self.assertEqual(decrypt(self.row().session_string_enc), VALID_SESSION)
        # null clears
        self.client.put(BASE, {'session_string': None}, format='json')
        self.assertEqual(self.row().session_string_enc, '')
        self.assertEqual(self.client.get(BASE).json()['effective_source'], 'env')

    def test_invalid_session_string_is_rejected(self):
        res = self.client.put(BASE, {'session_string': 'not-a-session'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(StorageSettings.objects.exclude(session_string_enc='').exists())

    def test_validation_errors(self):
        for payload in ({'chat_id': 'not a chat'}, {'alert_webhook_url': 'http://ntfy.example.com/x'},
                        {'alert_webhook_url': 'https://127.0.0.1/x'}, {'alert_min_interval_minutes': 4},
                        {'alert_min_interval_minutes': 1441}, {'alert_telegram_chat_id': 'abc'},
                        {'alert_format': 'email'}):
            with self.subTest(payload=payload), mock.patch.object(alerts, '_resolve', side_effect=REAL_RESOLVE):
                self.assertEqual(self.client.put(BASE, payload, format='json').status_code, 400)

    def test_secret_values_are_not_logged_when_settings_change(self):
        with self.assertLogs('storage_engine.views', level='INFO') as logs:
            self.client.put(BASE, {'alert_webhook_url': WEBHOOK, 'chat_id': '-100777'}, format='json')
        text = '\n'.join(r.getMessage() for r in logs.records)
        self.assertNotIn('my-topic', text)
        self.assertNotIn('100777', text)
        self.assertIn(str(self.admin.id), text)

    def test_credentials_unreadable_is_reported(self):
        StorageSettings.objects.update_or_create(pk=1, defaults={'session_string_enc': 'garbage-not-fernet'})
        body = self.client.get(BASE).json()
        self.assertTrue(body['credentials_unreadable'])
        self.assertEqual(self.client.post(BASE + 'test/').json(), {'ok': False, 'reason': 'credentials_unreadable'})

    def test_test_endpoint_runs_the_health_check(self):
        self.use_db_session('SESSION-A')
        self.assertEqual(self.client.post(BASE + 'test/').json(), {'ok': True, 'reason': ''})
        self.telegram.me = None
        self.assertEqual(self.client.post(BASE + 'test/').json(),
                         {'ok': False, 'reason': 'telegram_session_expired'})
        status_block = self.client.get(BASE).json()['status']
        self.assertEqual((status_block['last_check_ok'], status_block['last_check_reason'], status_block['alert_state']),
                         (False, 'telegram_session_expired', 'down'))

    def test_test_alert_requires_a_channel_then_reports_per_channel(self):
        self.assertEqual(self.client.post(BASE + 'test-alert/').status_code, 400)
        StorageSettings.get_solo()
        StorageSettings.objects.filter(pk=1).update(alert_webhook_url=WEBHOOK, alert_telegram_chat_id='42')
        with mock.patch.object(alerts.config, 'TELEGRAM_BOT_TOKEN', ''):
            res = self.client.post(BASE + 'test-alert/')
        results = res.json()['results']
        self.assertEqual(results['webhook'], 'ok')
        self.assertTrue(results['telegram'].startswith('error'))


class LoginWizardTests(AdminTestCase):
    def start(self, phone='+66 81 234 5678'):
        return self.client.post(BASE + 'login/start/', {'phone': phone}, format='json')

    def test_start_persists_pending_state_in_the_db_encrypted(self):
        res = self.start()
        self.assertEqual((res.status_code, res.json()), (200, {'ok': True, 'expires_in': 300}))
        self.assertEqual(self.telegram.code_requests, ['+66812345678'])
        row = self.row()
        self.assertEqual(decrypt(row.pending_login_session_enc), 'SESSION-1')
        self.assertEqual(decrypt(row.pending_code_hash), 'HASH-XYZ')
        self.assertNotIn('HASH-XYZ', row.pending_code_hash)
        self.assertTrue(self.client.get(BASE).json()['login_pending'])
        self.assertFalse(self.telegram.clients[0].connected)  # the start client is disconnected again

    def test_verify_success_saves_encrypted_session_and_recovers(self):
        StorageSettings.get_solo()
        StorageSettings.objects.filter(pk=1).update(alert_webhook_url=WEBHOOK)
        health.record_failure('telegram_session_expired')  # storage is down and an alert was sent
        self.sent.clear()
        self.start()
        res = self.client.post(BASE + 'login/verify/', {'code': ' 481 51 '}, format='json')
        body = res.json()
        self.assertEqual((res.status_code, body['ok'], body['account'], body['storage_ok']), (200, True, 'Alice', True))

        row = self.row()
        self.assertTrue(row.session_string_enc)
        self.assertNotIn('SESSION', row.session_string_enc)
        self.assertEqual(row.auth_mode, 'session')
        self.assertEqual(row.updated_by, self.admin)
        self.assertEqual((row.pending_login_session_enc, row.pending_phone, row.pending_code_hash, row.pending_expires_at),
                         ('', '', '', None))
        self.assertEqual(row.alert_state, 'ok')
        self.assertEqual(credentials.get_snapshot().session_str, decrypt(row.session_string_enc))
        self.assertEqual(credentials.get_snapshot().source, 'db')
        # a "recovered" alert went out
        self.assertTrue(any('recovered' in kwargs['headers']['Title'] for _, kwargs in self.sent))
        # the probe message was sent and removed
        self.assertEqual(self.telegram.store, {})

    def test_state_survives_between_requests_the_client_is_rebuilt_from_the_db_row(self):
        self.start()
        stored = decrypt(self.row().pending_login_session_enc)
        self.client.post(BASE + 'login/verify/', {'code': CODE}, format='json')
        call = self.telegram.sign_ins[0]
        self.assertEqual(call['session_str'], stored)
        self.assertEqual((call['phone'], call['code'], call['phone_code_hash']), ('+66812345678', CODE, 'HASH-XYZ'))

    def test_two_step_password_flow(self):
        self.start()
        self.telegram.script('sign_in', te.SessionPasswordNeededError(request=None))
        first = self.client.post(BASE + 'login/verify/', {'code': CODE}, format='json')
        self.assertEqual(first.json(), {'ok': False, 'needs_password': True})
        self.assertFalse(self.row().session_string_enc)
        self.assertTrue(self.client.get(BASE).json()['login_pending'])

        second = self.client.post(BASE + 'login/password/', {'password': PASSWORD}, format='json')
        self.assertEqual((second.status_code, second.json()['ok'], second.json()['account']), (200, True, 'Alice'))
        self.assertEqual(self.telegram.sign_ins[-1]['password'], PASSWORD)
        self.assertTrue(self.row().session_string_enc)
        self.assertFalse(self.client.get(BASE).json()['login_pending'])

    def test_wrong_password_is_400_and_keeps_the_pending_login(self):
        self.start()
        self.telegram.script('sign_in', te.SessionPasswordNeededError(request=None))
        self.client.post(BASE + 'login/verify/', {'code': CODE}, format='json')
        self.telegram.script('sign_in', te.PasswordHashInvalidError(request=None))
        res = self.client.post(BASE + 'login/password/', {'password': 'nope'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('password', res.json()['error'])
        self.assertTrue(self.client.get(BASE).json()['login_pending'])

    def test_wrong_and_expired_codes_are_400(self):
        self.start()
        self.telegram.script('sign_in', te.PhoneCodeInvalidError(request=None))
        wrong = self.client.post(BASE + 'login/verify/', {'code': '00000'}, format='json')
        self.assertEqual((wrong.status_code, wrong.json()['error']), (400, 'The code is incorrect.'))
        self.telegram.script('sign_in', te.PhoneCodeExpiredError(request=None))
        expired = self.client.post(BASE + 'login/verify/', {'code': CODE}, format='json')
        self.assertEqual(expired.status_code, 400)
        self.assertIn('expired', expired.json()['error'])
        self.assertFalse(self.row().session_string_enc)

    def test_expired_pending_login_is_ignored(self):
        self.start()
        StorageSettings.objects.filter(pk=1).update(pending_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertFalse(self.client.get(BASE).json()['login_pending'])
        res = self.client.post(BASE + 'login/verify/', {'code': CODE}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.telegram.sign_ins, [])

    def test_verify_without_start_is_400(self):
        self.assertEqual(self.client.post(BASE + 'login/verify/', {'code': CODE}, format='json').status_code, 400)

    def test_cancel_clears_pending(self):
        self.start()
        self.assertEqual(self.client.post(BASE + 'login/cancel/').status_code, 200)
        self.assertFalse(self.client.get(BASE).json()['login_pending'])
        self.assertEqual(self.row().pending_login_session_enc, '')

    def test_start_is_throttled_to_5_per_hour_per_user(self):
        for _ in range(5):
            self.assertEqual(self.start().status_code, 200)
        self.assertEqual(self.start().status_code, 429)

    def test_start_error_mapping(self):
        cases = [
            (te.PhoneNumberInvalidError(request=None), 400),
            (te.ApiIdInvalidError(request=None), 400),
            (te.FloodWaitError(request=None, capture=90), 429),
            (ConnectionError('down'), 503),
        ]
        for error, expected in cases:
            with self.subTest(error=type(error).__name__):
                cache.clear()
                self.telegram.script('send_code_request', error)
                res = self.start()
                self.assertEqual(res.status_code, expected)
                if expected == 429:
                    self.assertEqual(res['Retry-After'], '90')

    def test_invalid_phone_is_rejected_before_calling_telegram(self):
        self.assertEqual(self.start('0812345678').status_code, 400)
        self.assertEqual(self.telegram.code_requests, [])

    def test_missing_api_credentials_give_a_clear_400(self):
        with mock.patch('storage_engine.login.config.TELEGRAM_API_ID', 0):
            res = self.start()
        self.assertEqual(res.status_code, 400)
        self.assertIn('TELEGRAM_API_ID', res.json()['error'])

    def test_code_and_password_are_never_stored_returned_or_logged(self):
        with self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger('storage_engine').debug('capture-anchor')
            self.start()
            self.telegram.script('sign_in', te.SessionPasswordNeededError(request=None))
            r1 = self.client.post(BASE + 'login/verify/', {'code': CODE}, format='json')
            r2 = self.client.post(BASE + 'login/password/', {'password': PASSWORD}, format='json')
        text = '\n'.join(r.getMessage() for r in logs.records)
        stored = ' '.join(str(v) for v in StorageSettings.objects.filter(pk=1).values().first().values())
        for secret in (CODE, PASSWORD):
            self.assertNotIn(secret, text)
            self.assertNotIn(secret, stored)
            self.assertNotIn(secret, r1.content.decode() + r2.content.decode())
        # the saved session itself is not logged either
        self.assertNotIn('SESSION-', text)

    def test_login_probe_failure_still_saves_the_session_and_reports_the_step(self):
        self.start()
        self.telegram.script('send_file', te.ChatWriteForbiddenError(request=None))
        body = self.client.post(BASE + 'login/verify/', {'code': CODE}, format='json').json()
        self.assertTrue(body['ok'])
        self.assertFalse(body['storage_ok'])
        self.assertEqual((body['storage_step'], body['storage_reason']), ('upload', 'channel_unreachable'))
        self.assertTrue(self.row().session_string_enc)


class SelftestTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.use_db_session('SESSION-A')

    def test_success_reports_timings(self):
        result = run_selftest(1)
        self.assertTrue(result['ok'])
        self.assertIsNone(result['failed_step'])
        self.assertEqual(self.telegram.store, {})  # the test message was deleted

    def test_failure_at_each_step_names_the_step(self):
        cases = [
            ('send_file', te.ChatWriteForbiddenError(request=None), 'upload'),
            ('get_messages', te.AuthKeyUnregisteredError(request=None), 'download'),
            ('delete_messages', te.AuthKeyUnregisteredError(request=None), 'delete'),
        ]
        for method, error, step in cases:
            with self.subTest(step=step):
                self.reset_state()
                self.telegram.store.clear()
                self.telegram.script(method, error)
                result = run_selftest(1)
                self.assertFalse(result['ok'])
                self.assertEqual(result['failed_step'], step)
                self.assertTrue(result['reason'])

    def test_corrupted_download_fails_at_compare_and_cleans_up(self):
        original = self.telegram.build

        def corrupting_build(*args, **kwargs):
            client = original(*args, **kwargs)
            real_download = client.download_media

            async def download_media(msg, file=None):
                await real_download(msg, file=file)
                file.seek(0)
                file.write(b'\x00')

            client.download_media = download_media
            return client

        with mock.patch('storage_engine.client.build_telegram_client', side_effect=corrupting_build):
            result = run_selftest(1)
        self.assertEqual((result['ok'], result['failed_step']), (False, 'compare'))
        self.assertEqual(self.telegram.store, {})

    def test_admin_api_validates_size_and_runs(self):
        self.assertEqual(self.client.post(BASE + 'selftest/', {'size_mb': 17}, format='json').status_code, 400)
        self.assertEqual(self.client.post(BASE + 'selftest/', {'size_mb': 0}, format='json').status_code, 400)
        res = self.client.post(BASE + 'selftest/', {'size_mb': 1}, format='json')
        self.assertEqual((res.status_code, res.json()['ok']), (200, True))

    def test_management_command_prints_one_line_on_success(self):
        out = io.StringIO()
        with redirect_stdout(out):
            call_command('storage_selftest', '--size-mb', '1')
        line = out.getvalue().strip()
        self.assertRegex(line, r'^STORAGE SELFTEST OK size=1MB up=[\d.]+s down=[\d.]+s$')

    def test_management_command_failure_reports_step_and_reason(self):
        self.telegram.script('send_file', te.ChatWriteForbiddenError(request=None))
        with self.assertRaises(CommandError) as ctx:
            call_command('storage_selftest', '--size-mb', '1')
        self.assertEqual(str(ctx.exception), 'STORAGE SELFTEST FAILED step=upload reason=channel_unreachable')

    def test_management_command_rejects_bad_size(self):
        with self.assertRaises(CommandError):
            call_command('storage_selftest', '--size-mb', '99')
