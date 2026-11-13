import io
import time
import hashlib
import asyncio
import logging
import threading
from typing import Tuple
from django.conf import settings
from config.env_schema import config
from storage_engine import credentials, health
from storage_engine.errors import StorageEngineError, ContentUnavailable, StorageUnavailable

logger = logging.getLogger(__name__)

_sleep = asyncio.sleep  # indirection so tests can patch it
FLOOD_WAIT_MAX_SLEEP = 60  # longer waits are reported as 503 instead of blocking the request
FLOOD_WAIT_ATTEMPTS = 3


class BaseStorageEngine:
    def upload_chunk(self, chunk_data: bytes, filename: str) -> Tuple[int, str]:
        """Returns (message_id, file_id)"""
        raise NotImplementedError

    def download_chunk(self, file_id: str, message_id: int = None) -> bytes:
        """Returns raw chunk bytes"""
        raise NotImplementedError

    def delete_chunk(self, message_id: int) -> bool:
        """Deletes chunk from storage"""
        raise NotImplementedError

    def health_check(self) -> None:
        """Cheap liveness check (no upload). Raises StorageUnavailable when storage is down."""
        health.record_success(force=True)


class MockStorageEngine(BaseStorageEngine):
    """Local disk mock storage for development, testing, and CI"""
    def __init__(self, key='mock'):
        self.key = key
        self.last_used_at = time.monotonic()
        self.storage_dir = settings.CHUNK_CACHE_DIR / "mock_store"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def health_check(self) -> None:
        health.record_success(force=True, key=self.key)

    def disconnect(self):
        """Nothing persistent to close."""

    def upload_chunk(self, chunk_data: bytes, filename: str) -> Tuple[int, str]:
        chunk_hash = hashlib.sha256(chunk_data).hexdigest()
        file_path = self.storage_dir / f"{chunk_hash}.dat"
        file_path.write_bytes(chunk_data)
        message_id = int(time.time() * 1000) % 1000000000
        return message_id, chunk_hash

    def download_chunk(self, file_id: str, message_id: int = None) -> bytes:
        file_path = self.storage_dir / f"{file_id}.dat"
        if not file_path.exists():
            raise ContentUnavailable(f"Mock chunk {file_id} not found on disk")
        return file_path.read_bytes()

    def delete_chunk(self, message_id: int) -> bool:
        return True


class AsyncLoopThread:
    """Dedicated background daemon thread hosting a persistent asyncio event loop for Telethon."""
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True, name="TelethonLoopThread")
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run_coro(self, coro, timeout=180):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            future.cancel()  # do not leave a hung coroutine holding a semaphore
            raise


_telethon_thread = None
_thread_lock = threading.Lock()


def get_telethon_thread() -> AsyncLoopThread:
    global _telethon_thread
    with _thread_lock:
        if _telethon_thread is None:
            _telethon_thread = AsyncLoopThread()
        return _telethon_thread


def build_telegram_client(session_str: str, api_id: int, api_hash: str, allow_file_session: bool = True):
    """Builds a Telethon client. Tests patch this function to inject a fake client."""
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    if session_str or not allow_file_session:
        session = StringSession(session_str or None)
    else:
        session = str(settings.BASE_DIR / "telegram_storage")
    return TelegramClient(session, api_id, api_hash)


def _classify(exc: BaseException):
    """Maps a Telethon/network error to a StorageUnavailable reason, or None when unknown."""
    from telethon import errors as te

    session_errors = (
        te.AuthKeyUnregisteredError, te.SessionRevokedError, te.AuthKeyInvalidError,
        te.AuthKeyDuplicatedError, te.UnauthorizedError, te.UserDeactivatedError,
    )
    channel_errors = (
        te.ChatWriteForbiddenError, te.ChatAdminRequiredError, te.ChannelPrivateError,
        te.ChatIdInvalidError, te.PeerIdInvalidError,
    )
    if isinstance(exc, session_errors):
        return 'telegram_session_expired'
    if isinstance(exc, channel_errors):
        return 'channel_unreachable'
    if isinstance(exc, ValueError) and 'entity' in str(exc).lower():
        return 'channel_unreachable'  # Telethon: "Cannot find any entity corresponding to ..."
    if isinstance(exc, (ConnectionError, asyncio.TimeoutError, OSError)):
        return 'telegram_unreachable'
    return None


_chunk_lru_cache = {}
_chunk_lru_lock = threading.Lock()
MAX_CACHED_CHUNKS = 6  # 6 chunks * 20MB = 120MB maximum RAM buffer


class TelegramMTProtoEngine(BaseStorageEngine):
    """
    High-performance Telegram MTProto Client Storage Engine (Telethon).
    - Persistent warm TCP/MTProto connection (zero reconnect overhead per chunk).
    - Handles up to 2,000 MB per chunk natively without Bot API limits.
    - In-memory LRU chunk cache for ultra-fast Range seeking and PDF streaming.
    - True permanent deletion via client.delete_messages.
    - Credentials come from credentials.get_snapshot() (DB row, else env) and are re-checked
      on every call, so a changed session is picked up without a restart.
    - Database access happens only on the calling (synchronous) thread; coroutines on the
      Telethon loop thread never touch the ORM.
    """
    def __init__(self, key='system', creds_provider=None):
        self.key = key
        self._creds_provider = creds_provider or (lambda: credentials.get_snapshot())
        self.last_used_at = time.monotonic()
        self._thread = get_telethon_thread()
        self._client = None
        self._version = None
        self._lock = None
        self._upload_sem = None
        self._download_sem = None

    @property
    def chat_id(self):
        return self._creds_provider().chat_id

    async def _ensure_client(self, creds):
        async with self._lock:
            if self._client is not None and self._version != creds.version:
                logger.info("Telegram credentials changed; replacing the persistent client.")
                old, self._client = self._client, None
                try:
                    await old.disconnect()
                except Exception:
                    logger.warning("Disconnecting the old Telegram client failed", exc_info=True)

            if self._client is None:
                if not creds.api_id or not creds.api_hash:
                    raise StorageUnavailable('telegram_not_configured')
                # Only the system engine may fall back to the on-disk file session;
                # per-user engines must have an explicit session string.
                self._client = build_telegram_client(
                    creds.session_str, creds.api_id, creds.api_hash,
                    allow_file_session=(self.key == 'system'))
                self._version = creds.version
                await self._client.connect()
                logger.info("Persistent Telegram MTProto client connected and warmed up.")
            elif not self._client.is_connected():
                logger.info("Reconnecting persistent Telegram MTProto client...")
                await self._client.connect()

            return self._client

    async def _reconnect(self):
        client = self._client
        if client is None:
            return
        try:
            await client.disconnect()
            await client.connect()
        except Exception:
            logger.warning("Telegram reconnect failed", exc_info=True)

    async def _call(self, creds, label, op, which=None):
        """Runs `op(client)` under the upload/download semaphore (if any) with the error policy."""
        if self._lock is None:  # created on the loop thread; no await between check and set
            self._lock = asyncio.Lock()
            self._upload_sem = asyncio.Semaphore(3)
            self._download_sem = asyncio.Semaphore(4)
        sem = {'upload': self._upload_sem, 'download': self._download_sem}.get(which)
        if sem is None:
            return await self._attempts(creds, label, op)
        async with sem:
            return await self._attempts(creds, label, op)

    async def _attempts(self, creds, label, op):
        """
        session/channel errors -> 503 without retry, FloodWait <= 60s -> sleep and retry,
        network errors -> one reconnect + retry then 503, anything else -> StorageEngineError.
        """
        from telethon import errors as te

        flood_attempts = 0
        reconnected = False
        while True:
            try:
                client = await self._ensure_client(creds)
                return await op(client)
            except (StorageUnavailable, ContentUnavailable):
                raise
            except te.FloodWaitError as fwe:
                flood_attempts += 1
                if fwe.seconds > FLOOD_WAIT_MAX_SLEEP or flood_attempts >= FLOOD_WAIT_ATTEMPTS:
                    logger.warning("Telegram FloodWait %ss during %s; giving up", fwe.seconds, label)
                    raise StorageUnavailable('telegram_rate_limited', retry_after=max(fwe.seconds, 1)) from fwe
                logger.warning("Telegram FloodWait during %s: sleeping %ss (attempt %s)", label, fwe.seconds, flood_attempts)
                await _sleep(fwe.seconds)
            except Exception as exc:
                reason = _classify(exc)
                if reason is None:
                    logger.exception("Unexpected Telegram error during %s", label)
                    raise StorageEngineError(f"{label} failed: {type(exc).__name__}: {exc}") from exc
                if reason == 'telegram_unreachable' and not reconnected:
                    reconnected = True
                    logger.warning("Telegram connection problem during %s (%s); reconnecting once", label, type(exc).__name__)
                    await self._reconnect()
                    continue
                logger.warning("Telegram %s failed with reason=%s", label, reason, exc_info=True)
                raise StorageUnavailable(reason) from exc

    def _execute(self, label, op, which=None):
        """Synchronous entry point: resolves credentials, runs the call, records health/alerts."""
        self.last_used_at = time.monotonic()
        creds = self._creds_provider()
        try:
            if creds.unreadable:
                raise StorageUnavailable('credentials_unreadable')
            if self.key != 'system' and not creds.session_str:
                raise StorageUnavailable('storage_not_connected')
            if self.key != 'system' and not creds.chat_id:
                raise StorageUnavailable('channel_unreachable')
            result = self._thread.run_coro(self._call(creds, label, op, which))
        except StorageUnavailable as exc:
            health.record_failure(exc.reason, key=self.key)
            raise
        except TimeoutError as exc:
            health.record_failure('telegram_unreachable', key=self.key)
            raise StorageUnavailable('telegram_unreachable') from exc
        health.record_success(key=self.key)
        return result

    def upload_chunk(self, chunk_data: bytes, filename: str) -> Tuple[int, str]:
        """Uploads chunk directly to Telegram MTProto over persistent warm connection"""
        chat_id = self.chat_id

        async def op(client):
            file_stream = io.BytesIO(chunk_data)
            file_stream.name = filename
            # force_document=True ensures image chunks are NOT compressed or resized into Telegram photos
            msg = await client.send_file(
                chat_id, file_stream, caption=f"MTProto Cloud: {filename}", force_document=True
            )
            return msg.id, str(msg.id)

        return self._execute("upload", op, which='upload')

    def download_chunk(self, file_id: str, message_id: int = None) -> bytes:
        """Downloads chunk directly from Telegram MTProto into memory buffer with LRU cache"""
        msg_id = int(message_id) if message_id else int(file_id)
        cache_key = f"{self.key}:{file_id}_{msg_id}"
        with _chunk_lru_lock:
            if cache_key in _chunk_lru_cache:
                val = _chunk_lru_cache.pop(cache_key)
                _chunk_lru_cache[cache_key] = val
                return val

        chat_id = self.chat_id

        async def op(client):
            msg = await client.get_messages(chat_id, ids=msg_id)
            if not msg or not msg.media:
                raise ContentUnavailable(f"MTProto Message {msg_id} not found or contains no media")
            buffer = io.BytesIO()
            await client.download_media(msg, file=buffer)
            return buffer.getvalue()

        data = self._execute("download", op, which='download')

        with _chunk_lru_lock:
            if len(_chunk_lru_cache) >= MAX_CACHED_CHUNKS:
                oldest_key = next(iter(_chunk_lru_cache))
                del _chunk_lru_cache[oldest_key]
            _chunk_lru_cache[cache_key] = data

        return data

    def delete_chunk(self, message_id: int) -> bool:
        """
        Deletes chunk from Telegram directly and evicts it from the cache. Returns False on an
        unexpected failure (best effort); StorageUnavailable propagates so callers can report it.
        """
        with _chunk_lru_lock:
            keys_to_delete = [k for k in _chunk_lru_cache
                              if k.startswith(f"{self.key}:") and k.endswith(f"_{message_id}")]
            for k in keys_to_delete:
                del _chunk_lru_cache[k]

        chat_id = self.chat_id

        async def op(client):
            await client.delete_messages(chat_id, [message_id])
            return True

        try:
            return self._execute("delete", op)
        except StorageEngineError as exc:
            logger.warning("MTProto delete_messages failed: %s", exc)
            return False

    def health_check(self) -> None:
        """Connected client + get_me(), no upload. A None result means the session is not authorised."""
        async def op(client):
            me = await client.get_me()
            if me is None:
                raise StorageUnavailable('telegram_session_expired')
            return True

        self._execute("health check", op)

    def disconnect(self):
        """Disconnect the persistent client on the Telethon loop thread."""
        client = self._client
        if client is None or not client.is_connected():
            return
        try:
            self._thread.run_coro(client.disconnect())
        except Exception:
            logger.warning("Error disconnecting Telegram client for %s", self.key, exc_info=True)


_engine_pool = {}  # key -> engine; keys are 'system' or 'user:<account_id>'
_engine_lock = threading.Lock()
USER_ENGINE_IDLE_TTL = 900          # an idle per-user engine is disconnected after 15 min
USER_ENGINE_MAX_PER_WORKER = 32     # cap of live user engines per process


def _evict_user_engines(now):
    """Close engines idle for more than USER_ENGINE_IDLE_TTL, then trim to the per-worker cap."""
    idle_keys = [k for k, eng in _engine_pool.items()
                 if k != 'system' and now - getattr(eng, 'last_used_at', 0) > USER_ENGINE_IDLE_TTL]
    for k in idle_keys:
        eng = _engine_pool.pop(k)
        try:
            eng.disconnect()
        except Exception:
            pass
    user_keys = [k for k in _engine_pool if k != 'system']
    if len(user_keys) > USER_ENGINE_MAX_PER_WORKER:
        user_keys.sort(key=lambda k: getattr(_engine_pool[k], 'last_used_at', 0))
        for k in user_keys[: len(user_keys) - USER_ENGINE_MAX_PER_WORKER]:
            eng = _engine_pool.pop(k)
            try:
                eng.disconnect()
            except Exception:
                pass


def get_storage_engine(account=None) -> BaseStorageEngine:
    """
    One engine per key in a process-local pool: 'system' for the shared storage, 'user:<id>'
    per connected account. The Telegram engine is used when the DB row holds a session or env
    STORAGE_BACKEND=mtproto (unless auth_mode is 'mock'); the local-disk mock otherwise. User
    engines follow the same choice as the system engine.
    """
    if account is None:
        key = 'system'
    else:
        account_id = account.id if hasattr(account, 'id') else int(account)
        key = f"user:{account_id}"

    snap = credentials.get_snapshot()
    use_telegram = snap.mode != 'mock' and (config.STORAGE_BACKEND == "mtproto" or snap.source == 'db')

    with _engine_lock:
        _evict_user_engines(time.monotonic())
        if key in _engine_pool:
            existing = _engine_pool[key]
            if isinstance(existing, TelegramMTProtoEngine) == use_telegram:
                existing.last_used_at = time.monotonic()
                return existing
            # Class mismatch (mode switched between mock and mtproto), evict old.
            _engine_pool.pop(key)
            try:
                existing.disconnect()
            except Exception:
                pass
        if key == 'system':
            engine = (TelegramMTProtoEngine(key='system', creds_provider=credentials.get_snapshot)
                      if use_telegram else MockStorageEngine(key='system'))
        else:
            provider = lambda: credentials.get_account_snapshot(account_id)  # noqa: E731
            engine = (TelegramMTProtoEngine(key=key, creds_provider=provider)
                      if use_telegram else MockStorageEngine(key=key))
        _engine_pool[key] = engine
        _evict_user_engines(time.monotonic())  # run eviction so the pool never exceeds the user cap
        return engine
