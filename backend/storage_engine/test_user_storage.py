"""Per-user Telegram storage tests 1-10 of docs/plans/2026-11-13-per-user-storage.md.

Fakes only, no network. Uses StorageTestCase (fakes.py) which swaps the Telegram
client and the alert transport and resets the engine pool / credential cache.
"""
import logging
import time
from unittest import mock

from django.apps import apps
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from telethon import errors as te
from telethon.tl.types import InputPeerChannel

from importlib import import_module

from authentication.models import ApiToken
from drive.models import FileChunk, FileItem, Folder, StorageSettings, UploadSession, UserStorageAccount
from storage_engine import client as engine_client, credentials, health, login
from storage_engine.accounts import resolve_upload_target
from storage_engine.errors import StorageNotConnected, StorageUnavailable
from storage_engine.fakes import StorageTestCase
from storage_engine.secrets import decrypt, encrypt

# module name starts with a digit, so it cannot be imported with plain `import x.y.0004...`
_migration = import_module('authentication.migrations.'
                           '0004_user_system_storage_allowed_user_upload_target')
set_existing_users_system_storage = _migration.set_existing_users_system_storage

User = get_user_model()
ME = 5550001  # FakeTelegram.me.id: the Telegram account every fake login reports
CODE = '48151'
PASSWORD = 'correct horse battery staple'
PHONE = '+66 81 234 5678'
WEBHOOK = 'https://ntfy.example.com/alarm-topic'


class UserStorageTestCase(StorageTestCase):
    """Shared helpers. The system row holds a session so both system and user
    engines resolve to the real (fake) Telegram engine and client identity is observable."""

    def setUp(self):
        super().setUp()
        self.use_db_session('SYSTEM-1')

    def api(self, user, **credentials_kw):
        client = APIClient(raise_request_exception=False)
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def link_account(self, user, session='USER-1', channel=(777, 888), tg_user_id=None,
                     status=None, **fields):
        """A UserStorageAccount row; empty session means 'disconnected'."""
        if status is None:
            status = 'ok' if session else 'disconnected'
        account = UserStorageAccount.objects.create(
            user=user,
            session_string_enc=encrypt(session) if session else '',
            tg_user_id=tg_user_id, channel_id=channel[0], channel_access_hash=channel[1],
            tg_display_name='Alice', status=status, **fields)
        credentials.invalidate()
        return account

    # -- upload round-trip helpers -------------------------------------------------------------

    def initiate(self, client, size=10, filename='f.bin', folder_id=None):
        data = {'filename': filename, 'total_size': size}
        if folder_id:
            data['folder_id'] = str(folder_id)
        return client.post('/api/drive/uploads/initiate/', data, format='json')

    def put_chunk(self, client, session_id, data=b'A' * 10):
        return client.put(f'/api/drive/uploads/{session_id}/chunks/0/', data=data,
                          content_type='application/octet-stream')

    def complete(self, client, session_id, replace_file_id=None):
        body = {'replace_file_id': str(replace_file_id)} if replace_file_id else {}
        return client.post(f'/api/drive/uploads/{session_id}/complete/', body, format='json')

    def api_upload(self, client, size=10, **kwargs):
        """initiate -> chunk -> complete. Returns the complete response (and the session id)."""
        res = self.initiate(client, size=size, **kwargs)
        if res.status_code != 201:
            return res, None
        session_id = res.data['session_id']
        put = self.put_chunk(client, session_id, data=b'A' * size)
        if put.status_code != 200:
            return put, None
        return self.complete(client, session_id), session_id

    def upload_file(self, client, expect_account='any', size=10, **kwargs):
        """Upload one small file and return the FileItem (asserting the expected storage)."""
        res, _ = self.api_upload(client, size=size, **kwargs)
        self.assertEqual(res.status_code, 201)
        item = FileItem.objects.get(pk=res.data['id'])
        if expect_account is None:
            self.assertIsNone(item.storage_account)
        elif expect_account != 'any':
            self.assertEqual(item.storage_account_id, expect_account.id)
        return item

    def stream(self, client, file_id):
        return client.get(f'/api/drive/files/{file_id}/stream/')

    def set_target(self, user, target):
        """Persist upload_target so it survives refresh_from_db inside API views."""
        user.upload_target = target
        user.save(update_fields=['upload_target'])

    # -- engine introspection ------------------------------------------------------------------

    def user_engine(self, account):
        return engine_client._engine_pool[f'user:{account.id}']

    def system_engine(self):
        return engine_client._engine_pool['system']

    def instrument(self):
        """Record every Telegram call as (client, method, chat) from now on."""
        self.calls = []
        original_build = self.telegram.build

        def track(client):
            for method in ('send_file', 'get_messages', 'delete_messages'):
                op = getattr(client, method)

                async def spy(chat, *args, _method=method, _op=op, **kw):
                    self.calls.append((client, _method, chat))
                    return await _op(chat, *args, **kw)

                setattr(client, method, spy)
            return client

        def build(session_str, api_id, api_hash, allow_file_session=True):
            return track(original_build(session_str, api_id, api_hash, allow_file_session))

        patch = mock.patch.object(engine_client, 'build_telegram_client', side_effect=build)
        patch.start()
        self.addCleanup(patch.stop)

    def ops_for(self, client, method):
        return [chat for (c, m, chat) in self.calls if c is client and m == method]

    def built_clients(self):
        """The TelegramMTProtoEngine clients currently in the pool (they must exist)."""
        for engine in engine_client._engine_pool.values():
            self.assertIsNotNone(engine._client, f"engine {engine.key} built no client")
        return {engine.key: engine._client for engine in engine_client._engine_pool.values()}


# ------------------------------------------------------------------------ test 1: migration


class MigrationTests(UserStorageTestCase):
    def test_existing_users_get_system_storage_allowed_true(self):
        alice = User.objects.create_user(email='alice@example.com')
        bob = User.objects.create_user(email='bob@example.com')
        set_existing_users_system_storage(apps, None)  # the data step of migration 0004
        alice.refresh_from_db()
        bob.refresh_from_db()
        self.assertTrue(alice.system_storage_allowed)
        self.assertTrue(bob.system_storage_allowed)

    def test_new_users_default_to_own_storage(self):
        user = User.objects.create_user(email='new@example.com')
        self.assertFalse(user.system_storage_allowed)
        self.assertEqual(user.upload_target, 'own')
        self.assertFalse(user.can_use_system_storage)

    def test_legacy_file_without_storage_account_still_downloads(self):
        user = User.objects.create_user(email='legacy@example.com', system_storage_allowed=True)
        client = self.api(user)
        item = self.upload_file(client, expect_account=None, size=10)  # rule 3 -> system
        download = self.stream(client, item.id)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b''.join(download.streaming_content), b'A' * 10)


# ---------------------------------------------------------- test 2: resolve_upload_target


class ResolveUploadTargetTests(UserStorageTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email='resolver@example.com',
                                             system_storage_allowed=True)

    def test_rule1_system_target_with_grant_is_system(self):
        self.user.upload_target = 'system'
        self.assertIsNone(resolve_upload_target(self.user))

    def test_rule2_own_account_connected_wins(self):
        account = self.link_account(self.user)
        self.assertIs(resolve_upload_target(self.user), account)

    def test_rule2_applies_even_when_system_is_allowed(self):
        account = self.link_account(self.user)  # upload_target stays 'own'
        self.assertTrue(self.user.can_use_system_storage)
        self.assertEqual(resolve_upload_target(self.user).pk, account.pk)

    def test_rule3_falls_back_to_system_without_own(self):
        self.assertIsNone(resolve_upload_target(self.user))

    def test_rule4_raises_storage_not_connected(self):
        self.user.system_storage_allowed = False
        with self.assertRaises(StorageNotConnected) as ctx:
            resolve_upload_target(self.user)
        self.assertIn('Connect your Telegram account', str(ctx.exception))

    def test_rule4_maps_to_409_on_initiate(self):
        user = User.objects.create_user(email='stranded@example.com', system_storage_allowed=False)
        res = self.api(user).post('/api/drive/uploads/initiate/',
                                  {'filename': 'f.bin', 'total_size': 10}, format='json')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()['error'], 'storage_not_connected')
        self.assertIn('Settings → My storage', res.json()['message'])

    def test_superuser_can_always_use_system_storage(self):
        admin = User.objects.create_superuser(email='root@example.com', password='Password123!',
                                              system_storage_allowed=False)
        self.assertTrue(admin.can_use_system_storage)
        self.assertIsNone(resolve_upload_target(admin))  # rule 3 matches for superusers

    def test_superuser_system_target_without_grant_is_still_system(self):
        admin = User.objects.create_superuser(email='root2@example.com', password='Password123!',
                                              system_storage_allowed=False)
        admin.upload_target = 'system'
        self.assertIsNone(resolve_upload_target(admin))

    def test_revoked_grant_falls_through_to_own(self):
        account = self.link_account(self.user)
        self.user.upload_target = 'system'
        self.user.system_storage_allowed = False  # revoked; upload_target is left alone
        self.assertEqual(resolve_upload_target(self.user).pk, account.pk)

    def test_revoked_grant_without_own_account_raises(self):
        self.user.upload_target = 'system'
        self.user.system_storage_allowed = False
        with self.assertRaises(StorageNotConnected):
            resolve_upload_target(self.user)

    def test_revoked_user_can_still_read_and_delete_existing_system_files(self):
        self.user.upload_target = 'system'
        item = self.upload_file(self.api(self.user), expect_account=None)
        self.user.system_storage_allowed = False
        self.user.save(update_fields=['system_storage_allowed'])
        client = self.api(self.user)
        download = self.stream(client, item.id)
        self.assertEqual(download.status_code, 200)
        res = client.delete(f'/api/drive/files/{item.id}/')
        self.assertEqual(res.status_code, 200)


# ------------------------------------------------------------------- test 3: engine routing


class EngineRoutingTests(UserStorageTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email='router@example.com',
                                             system_storage_allowed=True)
        self.account = self.link_account(self.user)
        self.client = self.api(self.user)

    def test_own_upload_download_delete_use_the_accounts_channel_peer(self):
        self.instrument()
        item = self.upload_file(self.client, expect_account=self.account)
        clients = self.built_clients()
        self.assertIn(f'user:{self.account.id}', clients)
        user_client = clients[f'user:{self.account.id}']
        chunk_msg_id = FileChunk.objects.get(file_item=item).telegram_message_id
        # upload used the account's channel, never the system chat
        self.assertEqual(len(self.ops_for(user_client, 'send_file')), 1)
        self.assertIsInstance(self.ops_for(user_client, 'send_file')[0], InputPeerChannel)
        self.assertEqual((self.ops_for(user_client, 'send_file')[0].channel_id), 777)

        download = self.stream(self.client, item.id)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b''.join(download.streaming_content), b'A' * 10)
        self.assertEqual(self.ops_for(user_client, 'get_messages'),
                         [InputPeerChannel(777, 888)])

        res = self.client.delete(f'/api/drive/files/{item.id}/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(chunk_msg_id, self.telegram.deleted)
        self.assertEqual(self.ops_for(user_client, 'delete_messages'), [InputPeerChannel(777, 888)])
        # the system chat was never used anywhere on this path
        for (_, method, chat) in self.calls:
            self.assertNotEqual(chat, 'me')

    def test_own_upload_targets_the_stored_channel_peer_and_not_saved_messages(self):
        self.instrument()
        self.upload_file(self.client, expect_account=self.account)
        chats = [chat for (_, m, chat) in self.calls if m == 'send_file']
        self.assertEqual(chats, [InputPeerChannel(777, 888)])

    def test_system_files_use_the_system_engine_and_chat(self):
        self.instrument()
        self.user.upload_target = 'system'
        self.user.save(update_fields=['upload_target'])
        item = self.upload_file(self.client, expect_account=None)
        clients = self.built_clients()
        self.assertEqual(self.ops_for(clients['system'], 'send_file'), ['me'])
        res = self.client.delete(f'/api/drive/files/{item.id}/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.ops_for(clients['system'], 'delete_messages'), ['me'])

    def test_lru_cache_keys_do_not_mix_accounts_with_the_same_message_id(self):
        other = User.objects.create_user(email='other@example.com', system_storage_allowed=True)
        account_b = self.link_account(other, session='USER-2')

        engine_a = engine_client.get_storage_engine(account=self.account)
        msg_id, file_id = engine_a.upload_chunk(b'A' * 10, 'a.bin')
        self.assertEqual(engine_a.download_chunk(file_id, msg_id), b'A' * 10)  # fills user:A cache

        # another account must fetch its own bytes for the same message id, not hit account A's entry
        self.telegram.store[msg_id] = b'B' * 10
        engine_b = engine_client.get_storage_engine(account=account_b)
        self.assertEqual(engine_b.download_chunk(file_id, msg_id), b'B' * 10)
        keys = set(engine_client._chunk_lru_cache)
        self.assertIn(f'user:{self.account.id}:{file_id}_{msg_id}', keys)
        self.assertIn(f'user:{account_b.id}:{file_id}_{msg_id}', keys)
        # deleting through account A must only evict account A's key
        engine_a.delete_chunk(msg_id)
        keys = set(engine_client._chunk_lru_cache)
        self.assertNotIn(f'user:{self.account.id}:{file_id}_{msg_id}', keys)
        self.assertIn(f'user:{account_b.id}:{file_id}_{msg_id}', keys)

    def test_download_on_disconnected_own_account_is_503_storage_not_connected(self):
        item = self.upload_file(self.client, expect_account=self.account)
        self.account.session_string_enc = ''
        self.account.status = 'disconnected'
        self.account.save()
        engine_client._chunk_lru_cache.clear()
        res = self.stream(self.client, item.id)
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()['reason'], 'storage_not_connected')
        self.account.refresh_from_db()
        self.assertEqual(self.account.status, 'disconnected')

    def test_user_account_without_channel_raises_channel_unreachable_on_upload(self):
        user = User.objects.create_user(email='nochannel@example.com', system_storage_allowed=True)
        account = self.link_account(user, session='USER-NO-CHAN', channel=(None, None))
        client = self.api(user)
        res = self.initiate(client, size=10)
        self.assertEqual(res.status_code, 201)
        session_id = res.data['session_id']
        put = self.put_chunk(client, session_id, data=b'A' * 10)
        self.assertEqual(put.status_code, 503)
        self.assertEqual(put.json()['reason'], 'channel_unreachable')
        self.assertEqual(self.telegram.send_file_calls, 0)
        self.assertEqual(self.telegram.chats, [])

        engine = engine_client.get_storage_engine(account=account)
        with self.assertRaises(StorageUnavailable) as ctx:
            engine.upload_chunk(b'hello', 'test.bin')
        self.assertEqual(ctx.exception.reason, 'channel_unreachable')
        self.assertEqual(self.telegram.send_file_calls, 0)


# -------------------------------------------------------------------------- test 4: quota


class QuotaTests(UserStorageTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email='quota@example.com',
                                             system_storage_allowed=True)
        self.account = self.link_account(self.user)
        self.client = self.api(self.user)

    def set_target(self, user, target):
        """Persist upload_target so it survives refresh_from_db inside API views."""
        user.upload_target = target
        user.save(update_fields=['upload_target'])

    def reserved_used(self):
        self.user.refresh_from_db()
        return self.user.storage_reserved, self.user.storage_used

    def test_own_upload_reserves_nothing_and_never_touches_used(self):
        res, session_id = self.api_upload(self.client, size=100)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(self.reserved_used(), (0, 0))
        self.assertEqual(UploadSession.objects.get().storage_account_id, self.account.id)

    def test_system_upload_reserves_then_confirms(self):
        self.set_target(self.user, 'system')
        res = self.initiate(self.client, size=100)
        self.assertEqual(self.reserved_used(), (100, 0))
        self.put_chunk(self.client, res.data['session_id'], data=b'A' * 100)
        self.assertEqual(self.complete(self.client, res.data['session_id']).status_code, 201)
        self.assertEqual(self.reserved_used(), (0, 100))

    def test_replace_system_with_own_adjusts_used(self):
        self.set_target(self.user, 'system')
        res, _ = self.api_upload(self.client, size=100)
        old_id = res.data['id']
        self.assertEqual(self.reserved_used(), (0, 100))

        self.set_target(self.user, 'own')
        res, _ = self.complete_with(self.client, size=60, replace_file_id=old_id)
        self.assertEqual(res.status_code, 201)
        # old system bytes are freed, new own bytes cost nothing
        self.assertEqual(self.reserved_used(), (0, 0))
        self.assertEqual(FileItem.objects.get(pk=old_id).storage_account_id, self.account.id)

    def test_replace_own_with_system_adjusts_used(self):
        res, _ = self.api_upload(self.client, size=100)  # own (default target)
        old_id = res.data['id']
        self.assertEqual(self.reserved_used(), (0, 0))
        self.set_target(self.user, 'system')

        res, _ = self.complete_with(self.client, size=60, replace_file_id=old_id)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(self.reserved_used(), (0, 60))  # +60 used; own bytes contributed nothing
        self.assertIsNone(FileItem.objects.get(pk=old_id).storage_account)

    def complete_with(self, client, size, replace_file_id):
        res = self.initiate(client, size=size)
        if res.status_code != 201:
            return res, None
        session_id = res.data['session_id']
        put = self.put_chunk(client, session_id, data=b'A' * size)
        if put.status_code != 200:
            return put, None
        return self.complete(client, session_id, replace_file_id=replace_file_id), session_id

    def test_cancel_releases_only_system_reservations(self):
        self.set_target(self.user, 'system')
        res = self.initiate(self.client, size=500)
        self.assertEqual(self.reserved_used(), (500, 0))
        self.client.post(f"/api/drive/uploads/{res.data['session_id']}/cancel/", format='json')
        self.assertEqual(self.reserved_used(), (0, 0))

        self.set_target(self.user, 'own')
        res = self.initiate(self.client, size=500)
        self.assertEqual(self.reserved_used(), (0, 0))  # own uploads never reserve
        self.client.post(f"/api/drive/uploads/{res.data['session_id']}/cancel/", format='json')
        self.assertEqual(self.reserved_used(), (0, 0))

    def test_file_delete_reduces_only_system_bytes(self):
        self.set_target(self.user, 'system')
        system_item = self.upload_file(self.client, expect_account=None, size=100)
        self.set_target(self.user, 'own')
        own_item = self.upload_file(self.client, expect_account=self.account, size=50)
        self.assertEqual(self.reserved_used()[1], 100)

        self.client.delete(f'/api/drive/files/{own_item.id}/')
        self.assertEqual(self.reserved_used()[1], 100)  # own bytes were never counted
        self.client.delete(f'/api/drive/files/{system_item.id}/')
        self.assertEqual(self.reserved_used()[1], 0)    # only the system bytes are freed

    def test_folder_delete_reduces_only_system_bytes(self):
        folder = Folder.objects.create(name='stuff', owner=self.user)
        self.set_target(self.user, 'system')
        self.upload_file(self.client, expect_account=None, folder_id=folder.id)
        self.upload_file(self.client, expect_account=None, folder_id=folder.id)
        self.set_target(self.user, 'own')
        self.upload_file(self.client, expect_account=self.account, folder_id=folder.id)
        self.assertEqual(self.reserved_used()[1], 20)
        res = self.client.delete(f'/api/drive/folders/{folder.id}/')
        self.assertEqual(res.status_code, 204)
        self.assertEqual(self.reserved_used()[1], 0)
        self.assertEqual(FileItem.objects.count(), 0)


# ----------------------------------------------------- test 5: delete with disconnected own


class DisconnectedAccountDeleteTests(UserStorageTestCase):
    def test_deleting_an_own_file_when_the_account_is_disconnected_removes_the_rows(self):
        user = User.objects.create_user(email='ghost@example.com', system_storage_allowed=True)
        account = self.link_account(user, session='', tg_user_id=ME, status='disconnected')
        item = FileItem.objects.create(name='lost.bin', owner=user, size=11, storage_account=account)
        chunk = FileChunk.objects.create(file_item=item, chunk_index=0, telegram_message_id=4242,
                                         telegram_file_id='4242', chunk_size=11)
        with self.assertLogs('drive.views', level='WARNING') as logs:
            res = self.api(user).delete(f'/api/drive/files/{item.id}/')
        self.assertEqual(res.status_code, 200)  # no 503: the user may have lost that account
        self.assertFalse(FileItem.objects.filter(pk=item.id).exists())
        self.assertFalse(FileChunk.objects.filter(pk=chunk.pk).exists())
        text = '\n'.join(r.getMessage() for r in logs.records)
        self.assertIn(str(account.id), text)

    def test_folder_delete_with_disconnected_account_removes_rows(self):
        user = User.objects.create_user(email='ghost2@example.com', system_storage_allowed=True)
        account = self.link_account(user, session='', tg_user_id=ME, status='disconnected')
        folder = Folder.objects.create(name='stuff', owner=user)
        FileItem.objects.create(name='a.bin', owner=user, size=5, storage_account=account,
                                folder=folder)
        with self.assertLogs('drive.views', level='WARNING'):
            res = self.api(user).delete(f'/api/drive/folders/{folder.id}/')
        self.assertEqual(res.status_code, 204)
        self.assertFalse(FileItem.objects.filter(owner=user).exists())

    def test_replace_disconnected_own_file_with_system_upload_succeeds(self):
        user = User.objects.create_user(email='replacer@example.com', system_storage_allowed=True)
        account = self.link_account(user, session='', tg_user_id=ME, status='disconnected')
        item = FileItem.objects.create(name='ghost.bin', owner=user, size=50, storage_account=account)
        FileChunk.objects.create(file_item=item, chunk_index=0, telegram_message_id=999,
                                 telegram_file_id='999', chunk_size=50)

        self.set_target(user, 'system')
        client = self.api(user)
        init_res = self.initiate(client, size=60)
        self.assertEqual(init_res.status_code, 201)
        session_id = init_res.data['session_id']
        put_res = self.put_chunk(client, session_id, data=b'B' * 60)
        self.assertEqual(put_res.status_code, 200)

        with self.assertLogs('drive.views', level='WARNING') as logs:
            res = self.complete(client, session_id, replace_file_id=item.id)
        self.assertEqual(res.status_code, 201)
        item.refresh_from_db()
        self.assertIsNone(item.storage_account)
        self.assertEqual(item.size, 60)
        user.refresh_from_db()
        self.assertEqual(user.storage_used, 60)
        self.assertEqual(user.storage_reserved, 0)
        text = '\n'.join(r.getMessage() for r in logs.records)
        self.assertIn(str(account.id), text)


# --------------------------------------------------------------------------- test 6: pool


class EnginePoolTests(UserStorageTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email='pool@example.com')

    def test_user_engine_reloads_credentials_when_updated_at_changes(self):
        account = self.link_account(self.user, session='USER-1')
        engine = engine_client.get_storage_engine(account=account)
        engine.upload_chunk(b'a', 'f.bin')
        first_client = self.telegram.clients[-1]
        self.assertEqual(first_client.session_str, 'USER-1')

        account.session_string_enc = encrypt('USER-2')
        account.save()  # bumps updated_at: every worker must notice within 10 s
        credentials._user_checked_at[account.id] = 0.0  # pretend the window passed
        engine.upload_chunk(b'b', 'f.bin')

        self.assertEqual(self.telegram.clients[-1].session_str, 'USER-2')
        self.assertEqual(first_client.disconnect_calls, 1)  # the old client was closed

    def test_idle_engines_are_disconnected_after_fifteen_minutes(self):
        account = self.link_account(self.user)
        engine = engine_client.get_storage_engine(account=account)
        engine.upload_chunk(b'a', 'f.bin')
        client = self.telegram.clients[-1]
        engine.last_used_at = time.monotonic() - engine_client.USER_ENGINE_IDLE_TTL - 1
        engine_client.get_storage_engine()  # eviction runs inside every get_storage_engine
        self.assertNotIn(f'user:{account.id}', engine_client._engine_pool)
        self.assertEqual(client.disconnect_calls, 1)

    def test_cap_of_32_engines_evicts_the_least_recently_used(self):
        created = []
        for i in range(32):
            owner = User.objects.create_user(email=f'u{i}@example.com')
            acc = self.link_account(owner, session=f'U{i}', channel=(700 + i, 1))
            created.append(acc)
            engine_client.get_storage_engine(account=acc).upload_chunk(b'x', 'f.bin')
        system_engine = engine_client.get_storage_engine()  # keep a live system engine
        system_engine.last_used_at = time.monotonic() - 100000  # very idle: still never evicted

        extra = User.objects.create_user(email='u32@example.com')
        acc32 = self.link_account(extra, session='U32', channel=(732, 1))
        engine_client.get_storage_engine(account=acc32).upload_chunk(b'x', 'f.bin')

        user_keys = [k for k in engine_client._engine_pool if k != 'system']
        self.assertEqual(len(user_keys), 32)
        self.assertNotIn(f'user:{created[0].id}', engine_client._engine_pool)  # LRU first
        self.assertIn(f'user:{acc32.id}', engine_client._engine_pool)
        self.assertEqual(self.telegram.clients[0].disconnect_calls, 1)  # it was disconnected

    def test_system_engine_is_never_evicted(self):
        system_engine = engine_client.get_storage_engine()
        for i in range(engine_client.USER_ENGINE_MAX_PER_WORKER + 4):
            owner = User.objects.create_user(email=f'flood{i}@example.com')
            acc = self.link_account(owner, session=f'F{i}', channel=(1000 + i, 1))
            engine_client.get_storage_engine(account=acc)
        system_engine.last_used_at = time.monotonic() - 100000
        engine_client.get_storage_engine()  # runs eviction with a very idle system engine
        self.assertIn('system', engine_client._engine_pool)
        self.assertIs(engine_client._engine_pool['system'], system_engine)


# --------------------------------------------------------------------- test 7: health per key


class HealthPerKeyTests(UserStorageTestCase):
    def setUp(self):
        super().setUp()
        StorageSettings.objects.filter(pk=1).update(alert_webhook_url=WEBHOOK)
        self.user = User.objects.create_user(email='health@example.com',
                                             system_storage_allowed=True)
        self.account = self.link_account(self.user)
        self.other = User.objects.create_user(email='other-health@example.com',
                                              system_storage_allowed=True)
        self.other_account = self.link_account(self.other, session='USER-9')
        self.engine = engine_client.get_storage_engine(account=self.account)

    def trigger_user_failure(self):
        msg, file_id = self.engine.upload_chunk(b'x', 'f.bin')
        self.telegram.script('get_messages', te.AuthKeyUnregisteredError(request=None))
        with self.assertRaises(StorageUnavailable) as ctx:
            self.engine.download_chunk(file_id, msg)
        return ctx.exception

    def test_user_failure_does_not_alert_admin(self):
        exc = self.trigger_user_failure()
        self.assertEqual(exc.reason, 'telegram_session_expired')
        self.assertEqual(self.sent, [])  # nothing reached the alert transport
        self.assertEqual(StorageSettings.objects.get(pk=1).alert_state, 'ok')

    def test_user_failure_does_not_affect_system_or_other_users(self):
        self.trigger_user_failure()
        health.raise_if_known_down()  # system key: must not raise
        health.raise_if_known_down(key=f'user:{self.other_account.id}')  # other user key
        self.assertTrue(health.check_health()[0])  # system probe still healthy
        ok, _ = health.check_health(account=self.other_account, force=True)
        self.assertTrue(ok)

    def test_user_failure_marks_only_that_row_down(self):
        self.trigger_user_failure()
        self.account.refresh_from_db()
        self.assertEqual(self.account.status, 'down')
        self.assertEqual(self.account.last_check_reason, 'telegram_session_expired')
        self.other_account.refresh_from_db()
        self.assertNotEqual(self.other_account.status, 'down')
        # the failure must not write status back onto the system row's alert state
        self.assertEqual(StorageSettings.objects.get(pk=1).alert_state, 'ok')

    def test_folder_delete_prechecks_health_for_all_storages_before_deleting_chunks(self):
        user = User.objects.create_user(email='folderhealth@example.com', system_storage_allowed=True)
        account = self.link_account(user, session='USER-HEALTH')
        folder = Folder.objects.create(name='mixed-folder', owner=user)
        sys_file = FileItem.objects.create(name='sys.bin', owner=user, size=10, folder=folder, storage_account=None)
        FileChunk.objects.create(file_item=sys_file, chunk_index=0, telegram_message_id=101,
                                 telegram_file_id='101', chunk_size=10)
        user_file = FileItem.objects.create(name='user.bin', owner=user, size=20, folder=folder, storage_account=account)
        FileChunk.objects.create(file_item=user_file, chunk_index=0, telegram_message_id=102,
                                 telegram_file_id='102', chunk_size=20)

        health.record_failure('channel_unreachable', key=f'user:{account.id}')

        res = self.api(user).delete(f'/api/drive/folders/{folder.id}/')
        self.assertEqual(res.status_code, 503)
        self.assertEqual(self.telegram.deleted, [])
        self.assertTrue(FileItem.objects.filter(pk=sys_file.pk).exists())
        self.assertTrue(FileItem.objects.filter(pk=user_file.pk).exists())


# --------------------------------------------------------------------- test 8: user wizard


class UserWizardTests(UserStorageTestCase):
    BASE = '/api/storage/me/login/'

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email='wizard@example.com', password='Password123!')
        self.client = self.api(self.user)

    def start(self, phone=PHONE):
        return self.client.post(self.BASE + 'start/', {'phone': phone}, format='json')

    def row(self):
        return UserStorageAccount.objects.get(user=self.user)

    def verify(self, code=CODE):
        return self.client.post(self.BASE + 'verify/', {'code': code}, format='json')

    def test_start_then_verify_creates_channel_and_probes(self):
        res = self.start()
        self.assertEqual((res.status_code, res.json()), (200, {'ok': True, 'expires_in': 300}))
        row = self.row()
        self.assertEqual(decrypt(row.pending_login_session_enc), 'SESSION-1')
        self.assertEqual(decrypt(row.pending_code_hash), 'HASH-XYZ')
        self.assertEqual(self.telegram.code_requests, ['+66812345678'])
        self.assertEqual(row.pending_phone, '+66812345678')

        res = self.verify()
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual((body['ok'], body['account'], body['storage_ok']), (True, 'Alice', True))
        row.refresh_from_db()
        self.assertTrue(row.channel_id)  # created by CreateChannelRequest
        self.assertEqual(row.channel_access_hash, 123456789)
        self.assertEqual(row.tg_user_id, ME)
        self.assertEqual(row.status, 'ok')
        self.assertTrue(row.session_string_enc)
        self.assertNotIn('SESSION', row.session_string_enc)
        self.assertTrue(row.connected_at)
        self.assertEqual((row.pending_login_session_enc, row.pending_phone), ('', ''))

    def test_needs_password_path(self):
        self.start()
        self.telegram.script('sign_in', te.SessionPasswordNeededError(request=None))
        first = self.verify()
        self.assertEqual(first.json(), {'ok': False, 'needs_password': True})
        self.assertFalse(self.row().session_string_enc)
        self.assertTrue(self.client.get('/api/storage/me/').json()['login_pending'])

        second = self.client.post(self.BASE + 'password/', {'password': PASSWORD}, format='json')
        self.assertEqual((second.status_code, second.json()['ok'], second.json()['account']),
                         (200, True, 'Alice'))
        row = self.row()
        self.assertTrue(row.session_string_enc)
        self.assertEqual(row.status, 'ok')

    def test_telegram_account_linked_to_another_user_is_409_and_not_saved(self):
        squatter = User.objects.create_user(email='squatter@example.com')
        UserStorageAccount.objects.create(user=squatter, tg_user_id=ME, tg_display_name='Alice')
        self.start()
        res = self.verify()
        self.assertEqual(res.status_code, 409)
        self.assertIn('already linked to another user', res.json()['error'])
        self.assertEqual(self.row().session_string_enc, '')
        self.assertEqual(self.row().tg_user_id, None)
        self.assertEqual(self.telegram.log_out_calls, 1)
        self.assertEqual(self.row().pending_login_session_enc, '')

    def test_different_telegram_account_with_existing_files_is_409(self):
        account = self.link_account(self.user, session='', tg_user_id=999, status='disconnected',
                                    connected_at=None)
        FileItem.objects.create(name='mine.bin', owner=self.user, size=5, storage_account=account)
        self.start()
        res = self.verify()
        self.assertEqual(res.status_code, 409)
        self.assertIn('another Telegram account', res.json()['error'])
        self.assertEqual(self.row().session_string_enc, '')
        self.assertEqual(self.telegram.log_out_calls, 1)
        self.assertEqual(self.row().pending_login_session_enc, '')

    def test_finish_user_flood_wait_is_429(self):
        self.start()
        self.telegram.script('get_me', None, te.FloodWaitError(request=None, capture=45))
        res = self.verify()
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res['Retry-After'], '45')
        self.assertIn('Wait 45 seconds', res.json()['error'])
        self.assertEqual(self.telegram.log_out_calls, 1)
        self.assertEqual(self.row().pending_login_session_enc, '')

    def test_finish_user_channels_too_much_is_400(self):
        self.start()
        self.telegram.script('create_channel', te.ChannelsTooMuchError(request=None))
        res = self.verify()
        self.assertEqual(res.status_code, 400)
        self.assertIn('too many channels', res.json()['error'])
        self.assertEqual(self.telegram.log_out_calls, 1)
        self.assertEqual(self.row().pending_login_session_enc, '')

    def test_finish_user_connection_error_is_503(self):
        self.start()
        self.telegram.script('get_me', None, ConnectionError("Can't connect to TG"))
        res = self.verify()
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()['reason'], 'telegram_unreachable')
        self.assertEqual(self.telegram.log_out_calls, 1)
        self.assertEqual(self.row().pending_login_session_enc, '')

    def test_concurrent_race_integrity_error_is_409_and_logs_out(self):
        from django.db import IntegrityError
        self.start()
        orig_save = UserStorageAccount.save

        def fake_save(acc_inst, *args, **kwargs):
            if kwargs.get('update_fields') == acc_inst.PENDING_FIELDS:
                return orig_save(acc_inst, *args, **kwargs)
            raise IntegrityError("UNIQUE constraint failed: drive_userstorageaccount.tg_user_id")

        with mock.patch.object(UserStorageAccount, 'save', autospec=True, side_effect=fake_save):
            res = self.verify()
        self.assertEqual(res.status_code, 409)
        self.assertIn('already linked to another user', res.json()['error'])
        self.assertEqual(self.telegram.log_out_calls, 1)
        self.assertEqual(self.row().pending_login_session_enc, '')

    def test_same_account_reconnect_keeps_the_channel(self):
        self.link_account(self.user, session='', tg_user_id=ME, status='disconnected',
                          connected_at=None)
        channel_before = self.row().channel_id
        self.start()
        res = self.verify()
        self.assertEqual(res.status_code, 200)
        row = self.row()
        self.assertEqual(row.channel_id, channel_before)  # same account: not recreated
        self.assertEqual(row.status, 'ok')
        self.assertTrue(row.session_string_enc)

    def test_unreachable_channel_with_zero_files_is_recreated_once(self):
        self.start()
        self.telegram.script('send_file', te.ChatWriteForbiddenError(request=None))
        made = []

        def spy(client, _orig=login._create_channel):
            result = _orig(client)
            made.append(result)
            return result

        with mock.patch.object(login, '_create_channel', side_effect=spy) as created:
            res = self.verify()
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body['ok'])
        self.assertTrue(body['storage_ok'])  # worked once the channel was recreated
        self.assertEqual(created.call_count, 2)  # wizard's own + exactly one retry
        row = self.row()
        self.assertEqual(row.channel_id, made[-1][0])

    def test_unreachable_channel_with_files_does_not_recreate(self):
        self.link_account(self.user, session='', tg_user_id=ME, status='disconnected',
                          connected_at=None)
        FileItem.objects.create(name='mine.bin', owner=self.user, size=5,
                                storage_account=self.row())
        self.start()
        self.telegram.script('send_file', te.ChatWriteForbiddenError(request=None))
        with mock.patch.object(login, '_create_channel',
                               wraps=login._create_channel) as created:
            res = self.verify()
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()['storage_ok'])  # still reports the failed probe
        self.assertEqual(res.json()['storage_reason'], 'channel_unreachable')

    def test_start_is_throttled_to_five_per_hour(self):
        # distinct numbers: this checks the per-user limit, not the per-phone one
        for i in range(5):
            self.assertEqual(self.start(phone=f'+6681234560{i}').status_code, 200)
        self.assertEqual(self.start(phone='+66812345609').status_code, 429)

    def test_secrets_never_in_responses_or_logs(self):
        with self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger('storage_engine').debug('capture-anchor')
            self.start()
            self.telegram.script('sign_in', te.SessionPasswordNeededError(request=None))
            r1 = self.verify()
            r2 = self.client.post(self.BASE + 'password/', {'password': PASSWORD}, format='json')
            me_body = self.client.get('/api/storage/me/').content.decode()
        blob = r1.content.decode() + r2.content.decode() + me_body
        blob += '\n'.join(r.getMessage() for r in logs.records)
        for secret in (CODE, PASSWORD, 'SESSION-'):
            self.assertNotIn(secret, blob)
        row = self.row()
        for field in UserStorageAccount.PENDING_FIELDS:
            self.assertNotIn('SESSION', str(getattr(row, field)))


# ---------------------------------------------------- test 9: disconnect & pre-delete


class DisconnectAndPreDeleteTests(UserStorageTestCase):
    def test_disconnect_logs_out_clears_session_keeps_identity(self):
        user = User.objects.create_user(email='bye@example.com', system_storage_allowed=True)
        account = self.link_account(user, session='USER-1', tg_user_id=ME)
        res = self.api(user).post('/api/storage/me/disconnect/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.telegram.log_out_calls, 1)  # log_out was called on the client
        account.refresh_from_db()
        self.assertEqual(account.session_string_enc, '')
        self.assertEqual(account.status, 'disconnected')
        self.assertEqual(account.tg_user_id, ME)  # reconnecting restores the files
        self.assertEqual((account.channel_id, account.channel_access_hash), (777, 888))
        body = self.api(user).get('/api/storage/me/').json()
        self.assertFalse(body['own']['connected'])

    def test_user_delete_triggers_log_out(self):
        user = User.objects.create_user(email='gone@example.com', system_storage_allowed=True)
        self.link_account(user, session='USER-1')
        FileItem.objects.create(name='keep.bin', owner=user, size=1)  # exercises the PROTECT edge
        user.delete()
        self.assertEqual(self.telegram.log_out_calls, 1)
        self.assertFalse(UserStorageAccount.objects.filter(user_id=user.id).exists())
        self.assertFalse(FileItem.objects.filter(owner_id=user.id).exists())


# ---------------------------------------------------- test 10: permissions & admin API


class PermissionsAndAdminApiTests(UserStorageTestCase):
    ME_BASE = '/api/storage/me/'
    ADMIN_BASE = '/api/admin/users/'

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email='member@example.com', password='Password123!')
        self.admin = User.objects.create_superuser(email='root3@example.com', password='Password123!')
        plaintext = ApiToken.generate_plaintext()
        ApiToken.objects.create(user=self.user, name='t', prefix=plaintext[:12], scopes=['read'],
                                token_hash=ApiToken.hash_token(plaintext))
        self.bearer = APIClient(raise_request_exception=False)
        self.bearer.credentials(HTTP_AUTHORIZATION=f'Bearer {plaintext}')

    def test_storage_me_permissions(self):
        self.assertEqual(self.api(None).get(self.ME_BASE).status_code, 401)  # anonymous
        self.assertEqual(self.bearer.get(self.ME_BASE).status_code, 403)    # API tokens never
        member = self.api(self.user)
        res = member.get(self.ME_BASE)
        self.assertEqual(res.status_code, 200)  # any logged-in user, not only admins
        self.assertEqual(res.json()['own']['connected'], False)
        self.assertFalse(res.json()['system_allowed'])
        self.assertNotIn('6681', res.content.decode())  # no phone leak from the wizard
        # login endpoints behave the same way
        self.assertEqual(self.bearer.post(self.ME_BASE + 'login/start/', {'phone': PHONE},
                                          format='json').status_code, 403)
        self.assertEqual(self.api(None).post(self.ME_BASE + 'disconnect/').status_code, 401)

    def test_admin_users_permissions(self):
        member = self.api(self.user)
        self.assertEqual(member.get(self.ADMIN_BASE).status_code, 403)  # non-superuser
        self.assertEqual(self.bearer.get(self.ADMIN_BASE).status_code, 403)  # API token
        root = self.api(self.admin)
        res = root.get(self.ADMIN_BASE)
        self.assertEqual(res.status_code, 200)
        emails = [u['email'] for u in res.json()['results']]
        self.assertIn(self.user.email, emails)
        self.assertEqual(self.api(None).get(self.ADMIN_BASE).status_code, 401)

    def test_admin_cannot_deactivate_self(self):
        root = self.api(self.admin)
        res = root.patch(f'{self.ADMIN_BASE}{self.admin.id}/', {'is_active': False}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('yourself', res.json()['error'].lower())
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_patch_validates_storage_quota(self):
        root = self.api(self.admin)
        for bad in ('-1', 'abc'):
            with self.subTest(bad=bad):
                res = root.patch(f'{self.ADMIN_BASE}{self.user.id}/', {'storage_quota': bad},
                                 format='json')
                self.assertEqual(res.status_code, 400)
        res = root.patch(f'{self.ADMIN_BASE}{self.user.id}/', {'storage_quota': 0}, format='json')
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.storage_quota, 0)
        res = root.patch(f'{self.ADMIN_BASE}{self.user.id}/', {'storage_quota': None},
                         format='json')
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.storage_quota)

    def test_admin_patch_grants_system_storage_and_deactivates_another_user(self):
        root = self.api(self.admin)
        res = root.patch(f'{self.ADMIN_BASE}{self.user.id}/', {'system_storage_allowed': True},
                         format='json')
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.can_use_system_storage)
        res = root.patch(f'{self.ADMIN_BASE}{self.user.id}/', {'is_active': False}, format='json')
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
