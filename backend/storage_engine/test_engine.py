from unittest import mock

from django.test import override_settings
from rest_framework.test import APIClient
from telethon import errors as te

from django.contrib.auth import get_user_model
from drive.models import StorageSettings, UploadSession
from storage_engine import client as engine_client, credentials, health
from storage_engine.client import MockStorageEngine, TelegramMTProtoEngine, get_storage_engine
from storage_engine.errors import ContentUnavailable, StorageEngineError, StorageUnavailable
from storage_engine.fakes import StorageTestCase
from storage_engine.secrets import CredentialsUnreadable, decrypt, encrypt

User = get_user_model()


class CryptoAndCredentialsTests(StorageTestCase):
    def test_encrypt_round_trip_and_ciphertext_differs(self):
        token = encrypt('my-session')
        self.assertNotIn('my-session', token)
        self.assertEqual(decrypt(token), 'my-session')

    def test_wrong_key_is_credentials_unreadable_and_engine_returns_503(self):
        self.use_db_session('SESSION-A')
        with override_settings(SECRET_KEY='a-completely-different-secret-key-value'):
            with self.assertRaises(CredentialsUnreadable):
                decrypt(StorageSettings.get_solo().session_string_enc)
            credentials.invalidate()
            self.assertTrue(credentials.get_snapshot().unreadable)
            with self.assertRaises(StorageUnavailable) as ctx:
                get_storage_engine().upload_chunk(b'x', 'f.bin')
            self.assertEqual(ctx.exception.reason, 'credentials_unreadable')

    def test_no_db_row_uses_env_behaviour(self):
        self.assertFalse(StorageSettings.objects.exists())
        self.assertEqual(credentials.get_snapshot().source, 'env')
        self.assertIsInstance(get_storage_engine(), MockStorageEngine)  # env STORAGE_BACKEND=mock
        self.assertEqual(TelegramMTProtoEngine().chat_id, 'me')

    def test_db_session_wins_over_env_and_selects_telegram_engine(self):
        with mock.patch.object(credentials.config, 'TELEGRAM_SESSION_STRING', 'ENV-SESSION'):
            self.assertEqual(credentials.get_snapshot().session_str, 'ENV-SESSION')
            self.use_db_session('DB-SESSION')
            snap = credentials.get_snapshot()
            self.assertEqual((snap.source, snap.session_str), ('db', 'DB-SESSION'))
        self.assertIsInstance(get_storage_engine(), TelegramMTProtoEngine)

    def test_blank_db_chat_falls_back_to_env_then_me(self):
        row = self.use_db_session('S')
        self.assertEqual(credentials.get_snapshot().chat_id, 'me')
        row.chat_id = '-100123'
        row.save()
        credentials.invalidate()
        self.assertEqual(credentials.get_snapshot().chat_id, -100123)

    def test_hot_reload_replaces_client_when_updated_at_changes(self):
        self.use_db_session('SESSION-A')
        engine = get_storage_engine()
        engine.upload_chunk(b'one', 'a.bin')
        self.assertEqual(len(self.telegram.clients), 1)
        self.assertEqual(self.telegram.clients[0].session_str, 'SESSION-A')

        # same row, unchanged: re-check inside the 10 s window reuses the client
        engine.upload_chunk(b'two', 'b.bin')
        self.assertEqual(len(self.telegram.clients), 1)

        # credentials edited: other workers see the new updated_at and rebuild the client
        self.use_db_session('SESSION-B')
        credentials._checked_at = 0.0  # pretend the 10 s re-check interval has passed
        engine.upload_chunk(b'three', 'c.bin')
        self.assertEqual(len(self.telegram.clients), 2)
        self.assertEqual(self.telegram.clients[1].session_str, 'SESSION-B')
        self.assertEqual(self.telegram.clients[0].disconnect_calls, 1)

    def test_state_writes_do_not_bump_updated_at(self):
        row = self.use_db_session('S')
        before = StorageSettings.objects.get(pk=1).updated_at
        health.record_failure('telegram_unreachable')
        self.assertEqual(StorageSettings.objects.get(pk=1).updated_at, before)


class EnginePolicyTests(StorageTestCase):
    def setUp(self):
        super().setUp()
        self.use_db_session('SESSION-A')
        self.engine = get_storage_engine()

    def assert_unavailable(self, reason, call):
        with self.assertRaises(StorageUnavailable) as ctx:
            call()
        self.assertEqual(ctx.exception.reason, reason)
        return ctx.exception

    def test_upload_download_delete_round_trip(self):
        msg_id, file_id = self.engine.upload_chunk(b'hello', 'f.bin')
        self.assertEqual(self.engine.download_chunk(file_id, msg_id), b'hello')
        self.assertTrue(self.engine.delete_chunk(msg_id))
        self.assertIn(msg_id, self.telegram.deleted)

    def test_session_errors_are_503_without_retry(self):
        for error_class in (te.AuthKeyUnregisteredError, te.SessionRevokedError, te.AuthKeyInvalidError,
                            te.AuthKeyDuplicatedError, te.UnauthorizedError, te.UserDeactivatedError):
            with self.subTest(error=error_class.__name__):
                self.telegram.scripted.clear()

                def make():
                    try:
                        return error_class(request=None)
                    except TypeError:  # generic RPC errors also need a message
                        return error_class(request=None, message='UNAUTHORIZED')

                # a second scripted error would be consumed only if the engine retried
                self.telegram.script('send_file', make(), make())
                exc = self.assert_unavailable('telegram_session_expired', lambda: self.engine.upload_chunk(b'x', 'f'))
                self.assertEqual(len(self.telegram.scripted['send_file']), 1)
                self.assertEqual(exc.retry_after, 30)

    def test_channel_errors_are_503_channel_unreachable(self):
        for error in (te.ChatWriteForbiddenError(request=None), te.ChatAdminRequiredError(request=None),
                      te.ChannelPrivateError(request=None), te.ChatIdInvalidError(request=None),
                      ValueError('Cannot find any entity corresponding to "x"')):
            with self.subTest(error=type(error).__name__):
                self.telegram.script('send_file', error)
                self.assert_unavailable('channel_unreachable', lambda: self.engine.upload_chunk(b'x', 'f'))

    def test_flood_wait_over_60s_is_503_rate_limited_with_retry_after(self):
        self.telegram.script('send_file', te.FloodWaitError(request=None, capture=120))
        exc = self.assert_unavailable('telegram_rate_limited', lambda: self.engine.upload_chunk(b'x', 'f'))
        self.assertEqual(exc.retry_after, 120)
        self.assertEqual(self.sleeps, [])

    def test_flood_wait_up_to_60s_sleeps_and_retries(self):
        self.telegram.script('send_file', te.FloodWaitError(request=None, capture=5))
        msg_id, _ = self.engine.upload_chunk(b'x', 'f')
        self.assertEqual(self.sleeps, [5])
        self.assertIn(msg_id, self.telegram.store)

    def test_network_error_reconnects_once_then_succeeds(self):
        self.engine.upload_chunk(b'warm', 'w')
        self.telegram.script('send_file', ConnectionError('boom'))
        self.engine.upload_chunk(b'x', 'f')
        client = self.telegram.clients[0]
        self.assertEqual((client.disconnect_calls, client.connect_calls), (1, 2))

    def test_network_error_twice_is_503_unreachable(self):
        self.telegram.script('send_file', ConnectionError('boom'), TimeoutError())
        self.assert_unavailable('telegram_unreachable', lambda: self.engine.upload_chunk(b'x', 'f'))

    def test_unknown_error_is_storage_engine_error_with_traceback_logged(self):
        self.telegram.script('send_file', RuntimeError('weird'))
        with self.assertLogs('storage_engine.client', level='ERROR') as logs:
            with self.assertRaises(StorageEngineError) as ctx:
                self.engine.upload_chunk(b'x', 'f')
        self.assertNotIsInstance(ctx.exception, StorageUnavailable)
        self.assertTrue(logs.records[0].exc_info)

    def test_download_of_missing_message_is_content_unavailable(self):
        with self.assertRaises(ContentUnavailable):
            self.engine.download_chunk('9999', 9999)

    def test_failures_do_not_log_credentials(self):
        self.telegram.script('send_file', te.AuthKeyUnregisteredError(request=None))
        with self.assertLogs('storage_engine', level='DEBUG') as logs:
            with self.assertRaises(StorageUnavailable):
                self.engine.upload_chunk(b'x', 'f')
        self.assertNotIn('SESSION-A', '\n'.join(r.getMessage() for r in logs.records))

    def test_health_check_none_from_get_me_means_session_expired(self):
        self.telegram.me = None
        self.assert_unavailable('telegram_session_expired', self.engine.health_check)

    def test_missing_api_credentials_are_reported(self):
        with mock.patch.object(credentials.config, 'TELEGRAM_API_ID', 0):
            credentials.invalidate()
            self.assert_unavailable('telegram_not_configured', lambda: self.engine.upload_chunk(b'x', 'f'))


class ApiBehaviourTests(StorageTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email='u@example.com', password='Password123!',
                                             system_storage_allowed=True)
        self.client = APIClient(raise_request_exception=False)
        self.client.force_authenticate(user=self.user)
        self.use_db_session('SESSION-A')

    def initiate(self, size=10):
        return self.client.post('/api/drive/uploads/initiate/', {'filename': 'a.bin', 'total_size': size})

    def put_chunk(self, session_id, data=b'0123456789'):
        return self.client.put(
            f'/api/drive/uploads/{session_id}/chunks/0/', data=data, content_type='application/octet-stream'
        )

    def test_session_error_on_chunk_upload_is_503_with_reason_and_retry_after(self):
        session_id = self.initiate().data['session_id']
        self.telegram.script('send_file', te.AuthKeyUnregisteredError(request=None))
        res = self.put_chunk(session_id)
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()['error'], 'storage_unavailable')
        self.assertEqual(res.json()['reason'], 'telegram_session_expired')
        self.assertIn('message', res.json())
        self.assertEqual(res['Retry-After'], '30')

    def test_unknown_error_on_chunk_upload_is_500(self):
        session_id = self.initiate().data['session_id']
        self.telegram.script('send_file', RuntimeError('weird'))
        with self.assertLogs('storage_engine.client', level='ERROR'):
            res = self.put_chunk(session_id)
        self.assertEqual(res.status_code, 500)

    def test_initiate_returns_503_early_when_health_is_down_and_reserves_nothing(self):
        health.record_failure('telegram_session_expired')
        res = self.initiate(size=1000)
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()['reason'], 'telegram_session_expired')
        self.user.refresh_from_db()
        self.assertEqual(self.user.storage_reserved, 0)
        self.assertEqual(UploadSession.objects.count(), 0)

    def test_initiate_works_again_after_a_success_is_recorded(self):
        health.record_failure('telegram_session_expired')
        health.record_success()
        self.assertEqual(self.initiate().status_code, 201)

    def test_download_of_missing_message_is_410(self):
        session_id = self.initiate().data['session_id']
        self.assertEqual(self.put_chunk(session_id).status_code, 200)
        complete = self.client.post(f'/api/drive/uploads/{session_id}/complete/')
        self.assertEqual(complete.status_code, 201)
        self.telegram.store.clear()
        engine_client._chunk_lru_cache.clear()
        res = self.client.get(f"/api/drive/files/{complete.data['id']}/stream/")
        self.assertEqual(res.status_code, 410)
        self.assertEqual(res.json(), {'error': 'content_unavailable'})

    def test_download_when_session_expired_is_503(self):
        session_id = self.initiate().data['session_id']
        self.put_chunk(session_id)
        file_id = self.client.post(f'/api/drive/uploads/{session_id}/complete/').data['id']
        engine_client._chunk_lru_cache.clear()
        self.telegram.script('get_messages', te.AuthKeyUnregisteredError(request=None))
        res = self.client.get(f'/api/drive/files/{file_id}/stream/')
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()['reason'], 'telegram_session_expired')

    def test_delete_is_503_early_when_storage_known_down(self):
        session_id = self.initiate().data['session_id']
        self.put_chunk(session_id)
        file_id = self.client.post(f'/api/drive/uploads/{session_id}/complete/').data['id']
        health.record_failure('telegram_session_expired')
        res = self.client.delete(f'/api/drive/files/{file_id}/')
        self.assertEqual(res.status_code, 503)

    def test_delete_succeeds_locally_when_storage_fails_midway(self):
        session_id = self.initiate().data['session_id']
        self.put_chunk(session_id)
        file_id = self.client.post(f'/api/drive/uploads/{session_id}/complete/').data['id']
        self.telegram.script('delete_messages', te.AuthKeyUnregisteredError(request=None))
        with self.assertLogs('drive.views', level='WARNING'):
            res = self.client.delete(f'/api/drive/files/{file_id}/')
        self.assertEqual(res.status_code, 200)


class HealthEndpointTests(StorageTestCase):
    def test_mock_backend_is_ok(self):
        res = APIClient().get('/api/health/storage/')
        self.assertEqual((res.status_code, res.json()), (200, {'ok': True}))

    def test_down_is_503_without_secrets_or_chat_id(self):
        self.use_db_session('SESSION-A', chat_id='-100999')
        self.telegram.me = None
        res = APIClient().get('/api/health/storage/')
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json(), {'ok': False, 'reason': 'telegram_session_expired'})
        body = res.content.decode()
        self.assertNotIn('SESSION-A', body)
        self.assertNotIn('100999', body)

    def test_result_is_cached_for_30_seconds(self):
        self.use_db_session('SESSION-A')
        client = APIClient()
        self.assertEqual(client.get('/api/health/storage/').status_code, 200)
        self.telegram.me = None
        self.assertEqual(client.get('/api/health/storage/').status_code, 200)  # served from cache
        with mock.patch.object(health.time, 'monotonic', return_value=health.time.monotonic() + 31):
            self.assertEqual(client.get('/api/health/storage/').status_code, 503)

    def test_needs_no_authentication_even_with_a_bad_header(self):
        res = APIClient().get('/api/health/storage/', HTTP_AUTHORIZATION='Bearer tdk_garbage')
        self.assertEqual(res.status_code, 200)
