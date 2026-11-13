"""Regression tests for the security review of feat/per-user-storage (fakes only, no network)."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.db.models import F
from django.utils import timezone
from telethon import errors as te

from drive.models import FileChunk, FileItem, Folder, Permission, UploadSession
from storage_engine import client as engine_client
from storage_engine.secrets import encrypt
from storage_engine.selftest import run_selftest
from storage_engine.test_user_storage import CODE, ME, UserStorageTestCase

User = get_user_model()


def _file(owner, size=10, folder=None, account=None, msg_id=101):
    item = FileItem.objects.create(name=f'f{msg_id}.bin', owner=owner, size=size, folder=folder,
                                   storage_account=account)
    FileChunk.objects.create(file_item=item, chunk_index=0, telegram_message_id=msg_id,
                             telegram_file_id=str(msg_id), chunk_size=size)
    return item


class SuperuserCannotReachOwnStorageTests(UserStorageTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(email='root@example.com', password='Password123!')
        self.bob = User.objects.create_user(email='bob@example.com', password='Password123!')
        self.account = self.link_account(self.bob, session='BOB-1')
        self.own_file = _file(self.bob, account=self.account, msg_id=201)
        self.system_file = _file(self.bob, account=None, msg_id=202)
        self.root = self.api(self.admin)

    def test_superuser_cannot_stream_token_or_delete_a_file_on_a_users_own_telegram(self):
        self.assertEqual(self.stream(self.root, self.own_file.id).status_code, 403)
        self.assertEqual(self.root.get(f'/api/drive/files/{self.own_file.id}/media_token/').status_code, 403)
        self.assertEqual(self.root.delete(f'/api/drive/files/{self.own_file.id}/').status_code, 403)
        self.assertTrue(FileItem.objects.filter(pk=self.own_file.pk).exists())
        self.assertEqual(self.telegram.deleted, [])

    def test_superuser_keeps_access_to_system_storage_files(self):
        self.assertEqual(self.root.get(f'/api/drive/files/{self.system_file.id}/media_token/').status_code, 200)
        self.assertEqual(self.root.delete(f'/api/drive/files/{self.system_file.id}/').status_code, 200)
        self.assertFalse(FileItem.objects.filter(pk=self.system_file.pk).exists())


class QuotaCounterTests(UserStorageTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email='q@example.com', password='Password123!',
                                             system_storage_allowed=True)
        self.client_ = self.api(self.user)

    def test_folder_delete_does_not_overwrite_a_concurrent_quota_change(self):
        User.objects.filter(pk=self.user.pk).update(storage_used=50)
        folder = Folder.objects.create(name='big', owner=self.user)
        _file(self.user, size=10, folder=folder, msg_id=301)
        original = engine_client.TelegramMTProtoEngine.delete_chunk

        def delete_and_race(engine, message_id):
            # another request finishes a 100-byte system upload while Telegram is slow
            User.objects.filter(pk=self.user.pk).update(storage_used=F('storage_used') + 100)
            return original(engine, message_id)

        with mock.patch.object(engine_client.TelegramMTProtoEngine, 'delete_chunk', delete_and_race):
            res = self.client_.delete(f'/api/drive/folders/{folder.id}/')
        self.assertEqual(res.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.storage_used, 50 - 10 + 100)

    def test_detached_foreign_subfolder_keeps_the_owners_files_and_quota(self):
        viewer = User.objects.create_user(email='v@example.com', password='Password123!')
        top = Folder.objects.create(name='F', owner=self.user)
        Permission.objects.create(user=viewer, folder=top, role='editor')
        sub = Folder.objects.create(name='S', owner=viewer, parent=top)
        kept = _file(self.user, size=10, folder=sub, msg_id=401)
        User.objects.filter(pk=self.user.pk).update(storage_used=10)

        res = self.client_.delete(f'/api/drive/folders/{top.id}/')
        self.assertEqual(res.status_code, 204)
        self.assertTrue(FileItem.objects.filter(pk=kept.pk).exists())
        self.assertEqual(self.telegram.deleted, [])
        self.user.refresh_from_db()
        self.assertEqual(self.user.storage_used, 10)
        sub.refresh_from_db()
        self.assertIsNone(sub.parent_id)

    def test_revoked_system_grant_stops_an_open_system_upload(self):
        res = self.initiate(self.client_, size=10)
        self.assertEqual(res.status_code, 201)
        session_id = res.data['session_id']
        self.user.refresh_from_db()
        self.assertEqual(self.user.storage_reserved, 10)

        self.user.system_storage_allowed = False
        self.user.save(update_fields=['system_storage_allowed'])
        res = self.put_chunk(self.client_, session_id)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()['error'], 'storage_not_connected')
        self.assertEqual(UploadSession.objects.get(pk=session_id).status, 'CANCELLED')
        self.user.refresh_from_db()
        self.assertEqual(self.user.storage_reserved, 0)
        self.assertEqual(self.complete(self.client_, session_id).status_code, 400)


class AccountSwitchTests(UserStorageTestCase):
    def test_switching_telegram_account_cancels_open_uploads_and_purges_cache(self):
        user = User.objects.create_user(email='switch@example.com', password='Password123!')
        account = self.link_account(user, session='', tg_user_id=ME + 1, status='disconnected')
        session = UploadSession.objects.create(
            user=user, filename='x.bin', total_size=10, total_chunks=1,
            expires_at=timezone.now() + timedelta(hours=1), storage_account=account)
        engine_client._chunk_lru_cache[f'user:{account.id}:1_1'] = b'old'
        engine_client._chunk_lru_cache['system:1_1'] = b'keep'

        client = self.api(user)
        client.post('/api/storage/me/login/start/', {'phone': '+66812345678'}, format='json')
        res = client.post('/api/storage/me/login/verify/', {'code': CODE}, format='json')
        self.assertEqual(res.status_code, 200)
        session.refresh_from_db()
        self.assertEqual(session.status, 'CANCELLED')
        self.assertNotIn(f'user:{account.id}:1_1', engine_client._chunk_lru_cache)
        self.assertIn('system:1_1', engine_client._chunk_lru_cache)


class AdminPatchTests(UserStorageTestCase):
    def test_string_false_revokes_instead_of_granting(self):
        admin = User.objects.create_superuser(email='root2@example.com', password='Password123!')
        user = User.objects.create_user(email='p@example.com', password='Password123!',
                                        system_storage_allowed=True)
        res = self.api(admin).patch(f'/api/admin/users/{user.pk}/',
                                    {'system_storage_allowed': 'false', 'is_active': '0'}, format='json')
        self.assertEqual(res.status_code, 200)
        user.refresh_from_db()
        self.assertEqual((user.system_storage_allowed, user.is_active), (False, False))

    def test_negative_or_garbage_quota_is_400(self):
        admin = User.objects.create_superuser(email='root3@example.com', password='Password123!')
        user = User.objects.create_user(email='p2@example.com', password='Password123!')
        for value in (-1, 'lots'):
            res = self.api(admin).patch(f'/api/admin/users/{user.pk}/', {'storage_quota': value}, format='json')
            self.assertEqual(res.status_code, 400)


class SelftestReasonTests(UserStorageTestCase):
    def test_reason_is_the_class_name_only(self):
        user = User.objects.create_user(email='s@example.com', password='Password123!')
        account = self.link_account(user, session='SELF-1')
        self.telegram.script('send_file', RuntimeError('InputPeerChannel(channel_id=777, access_hash=888)'))
        result = run_selftest(1, account=account)
        self.assertFalse(result['ok'])
        self.assertNotIn('888', result['reason'])
        self.assertNotIn('777', result['reason'])


class PendingLoginTests(UserStorageTestCase):
    def test_expired_pending_login_is_cleared_including_the_phone(self):
        user = User.objects.create_user(email='e@example.com', password='Password123!')
        account = self.link_account(
            user, session='', status='disconnected',
            pending_login_session_enc=encrypt('HALF'), pending_phone='+66812345678',
            pending_code_hash=encrypt('HASH'), pending_expires_at=timezone.now() - timedelta(minutes=1))
        res = self.api(user).post('/api/storage/me/login/verify/', {'code': CODE}, format='json')
        self.assertEqual(res.status_code, 400)
        account.refresh_from_db()
        self.assertEqual((account.pending_phone, account.pending_login_session_enc), ('', ''))


class LoginStartThrottleTests(UserStorageTestCase):
    def start(self, user, phone):
        return self.api(user).post('/api/storage/me/login/start/', {'phone': phone}, format='json')

    def test_per_phone_limit(self):
        user = User.objects.create_user(email='t1@example.com', password='Password123!')
        for _ in range(3):
            self.assertEqual(self.start(user, '+66 81 111 1111').status_code, 200)
        self.assertEqual(self.start(user, '+66811111111').status_code, 429)  # same number, other spelling
        self.assertEqual(self.start(user, '+66822222222').status_code, 200)

    def test_per_ip_limit_across_accounts(self):
        users = [User.objects.create_user(email=f'ip{i}@example.com', password='Password123!') for i in range(3)]
        codes = []
        for n in range(11):
            codes.append(self.start(users[n // 4], f'+668300000{n:02d}').status_code)
        self.assertEqual(codes[:10], [200] * 10)
        self.assertEqual(codes[10], 429)
