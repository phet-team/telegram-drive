"""Test doubles for Telegram and the alert transport. Nothing here touches the network."""
import itertools
from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from storage_engine import alerts, client as engine_client, credentials, health
from storage_engine.secrets import encrypt

PUBLIC_IP = '93.184.216.34'
REAL_RESOLVE = alerts._resolve  # captured before StorageTestCase patches it (literal IPs resolve offline)


class FakeSession:
    def __init__(self, label):
        self.label = label

    def save(self):
        return f"SESSION-{self.label}"


class FakeClient:
    def __init__(self, world, session_str):
        self.world = world
        self.session_str = session_str
        self.session = FakeSession(f"{world.next_session()}")
        self.connected = False
        self.connect_calls = 0
        self.disconnect_calls = 0

    async def connect(self):
        self.connect_calls += 1
        self.connected = True

    async def disconnect(self):
        self.disconnect_calls += 1
        self.connected = False

    def is_connected(self):
        return self.connected

    async def send_file(self, chat, stream, caption=None, force_document=False):
        self.world.raise_scripted('send_file')
        self.world.send_file_calls += 1
        message_id = next(self.world.ids)
        self.world.store[message_id] = stream.getvalue()
        self.world.chats.append(chat)
        return SimpleNamespace(id=message_id)

    async def get_messages(self, chat, ids=None):
        self.world.raise_scripted('get_messages')
        if ids in self.world.store:
            return SimpleNamespace(id=ids, media=True)
        return None

    async def download_media(self, msg, file=None):
        self.world.raise_scripted('download_media')
        file.write(self.world.store[msg.id])

    async def delete_messages(self, chat, ids):
        self.world.raise_scripted('delete_messages')
        for message_id in ids:
            self.world.store.pop(message_id, None)
            self.world.deleted.append(message_id)

    async def get_me(self):
        self.world.raise_scripted('get_me')
        return self.world.me

    async def send_code_request(self, phone):
        self.world.raise_scripted('send_code_request')
        self.world.code_requests.append(phone)
        return SimpleNamespace(phone_code_hash='HASH-XYZ')

    async def sign_in(self, phone=None, code=None, *, password=None, phone_code_hash=None):
        self.world.raise_scripted('sign_in')
        self.world.sign_ins.append(
            {'phone': phone, 'code': code, 'password': password, 'phone_code_hash': phone_code_hash,
             'session_str': self.session_str}
        )
        return self.world.me

    async def log_out(self):
        self.world.log_out_calls += 1
        return True

    async def __call__(self, request):
        """Telethon clients are callable for TL requests; the fake understands channel creation."""
        from telethon.tl.functions.channels import CreateChannelRequest

        if isinstance(request, CreateChannelRequest):
            chat = SimpleNamespace(id=next(self.world.ids), access_hash=123456789)
            return SimpleNamespace(chats=[chat])
        raise NotImplementedError(f"FakeClient.__call__ {request}")


class FakeTelegram:
    """Shared state behind every FakeClient: stored messages, scripted errors, recorded calls."""

    def __init__(self):
        self.ids = itertools.count(1000)
        self._sessions = itertools.count(1)
        self.store = {}
        self.deleted = []
        self.chats = []
        self.code_requests = []
        self.sign_ins = []
        self.log_out_calls = 0
        self.send_file_calls = 0
        self.clients = []
        self.me = SimpleNamespace(first_name='Alice', id=5550001)
        self.scripted = {}  # method name -> list of exceptions raised one per call, in order

    def next_session(self):
        return next(self._sessions)

    def script(self, method, *errors):
        self.scripted.setdefault(method, []).extend(errors)

    def raise_scripted(self, method):
        queue = self.scripted.get(method)
        if queue:
            error = queue.pop(0)
            if error is not None:
                raise error

    def build(self, session_str, api_id, api_hash, allow_file_session=True):
        client = FakeClient(self, session_str)
        self.clients.append(client)
        return client


class StorageTestCase(TestCase):
    """Resets every module-level cache and swaps the Telegram client and alert transport for fakes."""

    def setUp(self):
        cache.clear()
        self.telegram = FakeTelegram()
        self.sent = []  # (url, kwargs) of every alert HTTP POST
        self.sleeps = []

        async def fake_sleep(seconds):
            self.sleeps.append(seconds)

        def fake_post(url, **kwargs):
            self.sent.append((url, kwargs))
            return SimpleNamespace(status_code=200)

        patches = [
            mock.patch.object(engine_client, 'build_telegram_client', side_effect=self.telegram.build),
            mock.patch.object(engine_client, '_sleep', fake_sleep),
            mock.patch.object(alerts, '_post', side_effect=fake_post),
            mock.patch.object(alerts, '_resolve', return_value=[PUBLIC_IP]),
            mock.patch.object(alerts, '_run_in_background', side_effect=lambda fn: fn()),
            mock.patch.object(credentials.config, 'TELEGRAM_API_ID', 12345),
            mock.patch.object(credentials.config, 'TELEGRAM_API_HASH', 'fake-hash'),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.reset_state()
        self.addCleanup(self.reset_state)

    @staticmethod
    def reset_state():
        engine_client._engine_pool.clear()
        engine_client._chunk_lru_cache.clear()
        credentials.invalidate()  # system snapshot and every user snapshot
        health.reset()

    def use_db_session(self, session='SESSION-A', **fields):
        from drive.models import StorageSettings
        row = StorageSettings.get_solo()
        row.session_string_enc = encrypt(session)
        for name, value in fields.items():
            setattr(row, name, value)
        row.save()
        credentials.invalidate()
        return row
