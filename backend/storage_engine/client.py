import os
import io
import time
import hashlib
import asyncio
import logging
import threading
from pathlib import Path
from typing import Tuple
from django.conf import settings
from config.env_schema import config

logger = logging.getLogger(__name__)


class StorageEngineError(Exception):
    pass


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


class MockStorageEngine(BaseStorageEngine):
    """Local disk mock storage for development, testing, and CI"""
    def __init__(self):
        self.storage_dir = settings.CHUNK_CACHE_DIR / "mock_store"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def upload_chunk(self, chunk_data: bytes, filename: str) -> Tuple[int, str]:
        chunk_hash = hashlib.sha256(chunk_data).hexdigest()
        file_path = self.storage_dir / f"{chunk_hash}.dat"
        file_path.write_bytes(chunk_data)
        message_id = int(time.time() * 1000) % 1000000000
        return message_id, chunk_hash

    def download_chunk(self, file_id: str, message_id: int = None) -> bytes:
        file_path = self.storage_dir / f"{file_id}.dat"
        if not file_path.exists():
            raise StorageEngineError(f"Mock chunk {file_id} not found on disk")
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
        return future.result(timeout=timeout)


_telethon_thread = None
_thread_lock = threading.Lock()


def get_telethon_thread() -> AsyncLoopThread:
    global _telethon_thread
    with _thread_lock:
        if _telethon_thread is None:
            _telethon_thread = AsyncLoopThread()
        return _telethon_thread


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
    """
    def __init__(self):
        self.api_id = config.TELEGRAM_API_ID
        self.api_hash = config.TELEGRAM_API_HASH
        self.session_str = config.TELEGRAM_SESSION_STRING

        chat_val = (config.TELEGRAM_STORAGE_CHAT_ID or "").strip()
        if not chat_val:
            self.chat_id = 'me'  # Default to 'Saved Messages' (Personal cloud)
        elif chat_val.lstrip('-').isdigit():
            self.chat_id = int(chat_val)
        else:
            self.chat_id = chat_val

        self._thread = get_telethon_thread()
        self._client = None
        self._lock = None
        self._upload_sem = None
        self._download_sem = None

    async def _ensure_client(self):
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        if self._lock is None:
            self._lock = asyncio.Lock()
            self._upload_sem = asyncio.Semaphore(3)
            self._download_sem = asyncio.Semaphore(4)

        async with self._lock:
            if self._client is None:
                if self.session_str:
                    session = StringSession(self.session_str)
                else:
                    session = str(settings.BASE_DIR / "telegram_storage")

                self._client = TelegramClient(session, self.api_id, self.api_hash)
                await self._client.connect()
                logger.info("Persistent Telegram MTProto client connected and warmed up.")
            elif not self._client.is_connected():
                logger.info("Reconnecting persistent Telegram MTProto client...")
                await self._client.connect()

            return self._client

    async def _async_upload(self, chunk_data: bytes, filename: str) -> Tuple[int, str]:
        from telethon import errors as telethon_errors

        await self._ensure_client()
        async with self._upload_sem:
            for attempt in range(3):
                try:
                    file_stream = io.BytesIO(chunk_data)
                    file_stream.name = filename
                    # Reusing already warm client connection
                    # force_document=True ensures image chunks are NOT compressed or resized into Telegram photos
                    msg = await self._client.send_file(
                        self.chat_id,
                        file_stream,
                        caption=f"MTProto Cloud: {filename}",
                        force_document=True
                    )
                    return msg.id, str(msg.id)
                except telethon_errors.FloodWaitError as fwe:
                    logger.warning(f"Telegram FloodWaitError: sleeping {fwe.seconds}s (attempt {attempt + 1}/3)")
                    await asyncio.sleep(fwe.seconds)
                    if attempt == 2:
                        raise StorageEngineError(f"Upload aborted after FloodWait: {fwe}")
                except Exception as e:
                    logger.warning(f"Telegram upload attempt {attempt + 1} failed: {e}")
                    if attempt == 2:
                        raise StorageEngineError(f"Upload failed: {e}")
                    # Attempt quick reconnection if connection dropped
                    try:
                        if not self._client.is_connected():
                            await self._client.connect()
                    except Exception:
                        pass
                    await asyncio.sleep(1)

    async def _async_download(self, message_id: int) -> bytes:
        from telethon import errors as telethon_errors

        await self._ensure_client()
        async with self._download_sem:
            for attempt in range(3):
                try:
                    msg = await self._client.get_messages(self.chat_id, ids=message_id)
                    if not msg or not msg.media:
                        raise StorageEngineError(f"MTProto Message {message_id} not found or contains no media")
                    buffer = io.BytesIO()
                    await self._client.download_media(msg, file=buffer)
                    return buffer.getvalue()
                except telethon_errors.FloodWaitError as fwe:
                    logger.warning(f"Telegram FloodWaitError during download: sleeping {fwe.seconds}s (attempt {attempt + 1}/3)")
                    await asyncio.sleep(fwe.seconds)
                    if attempt == 2:
                        raise StorageEngineError(f"Download aborted after FloodWait: {fwe}")
                except Exception as e:
                    logger.warning(f"Telegram download attempt {attempt + 1} failed: {e}")
                    if attempt == 2:
                        raise StorageEngineError(f"Download failed: {e}")
                    try:
                        if not self._client.is_connected():
                            await self._client.connect()
                    except Exception:
                        pass
                    await asyncio.sleep(1)

    async def _async_delete(self, message_id: int) -> bool:
        await self._ensure_client()
        try:
            await self._client.delete_messages(self.chat_id, [message_id])
            return True
        except Exception as e:
            logger.warning(f"MTProto delete_messages failed: {e}")
            return False

    def upload_chunk(self, chunk_data: bytes, filename: str) -> Tuple[int, str]:
        """Uploads chunk directly to Telegram MTProto over persistent warm connection"""
        return self._thread.run_coro(self._async_upload(chunk_data, filename))

    def download_chunk(self, file_id: str, message_id: int = None) -> bytes:
        """Downloads chunk directly from Telegram MTProto into memory buffer with LRU cache"""
        msg_id = int(message_id) if message_id else int(file_id)
        cache_key = f"{file_id}_{msg_id}"
        with _chunk_lru_lock:
            if cache_key in _chunk_lru_cache:
                val = _chunk_lru_cache.pop(cache_key)
                _chunk_lru_cache[cache_key] = val
                return val

        data = self._thread.run_coro(self._async_download(msg_id))

        with _chunk_lru_lock:
            if len(_chunk_lru_cache) >= MAX_CACHED_CHUNKS:
                oldest_key = next(iter(_chunk_lru_cache))
                del _chunk_lru_cache[oldest_key]
            _chunk_lru_cache[cache_key] = data

        return data

    def delete_chunk(self, message_id: int) -> bool:
        """Deletes chunk from Telegram channel directly and evicts from cache"""
        with _chunk_lru_lock:
            keys_to_delete = [k for k in _chunk_lru_cache if f"_{message_id}" in k]
            for k in keys_to_delete:
                del _chunk_lru_cache[k]
        return self._thread.run_coro(self._async_delete(message_id))


_engine_instance = None
_engine_lock = threading.Lock()


def get_storage_engine() -> BaseStorageEngine:
    global _engine_instance
    with _engine_lock:
        if _engine_instance is None:
            if config.STORAGE_BACKEND == "mtproto":
                _engine_instance = TelegramMTProtoEngine()
            else:
                _engine_instance = MockStorageEngine()
        return _engine_instance
