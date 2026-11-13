"""
Where the engine gets its Telegram credentials: the StorageSettings DB row when it
holds a session, otherwise the environment (exactly the pre-DB behaviour).

The snapshot is re-validated against the row's `updated_at` at most every
RELOAD_INTERVAL seconds, so every gunicorn worker picks up a change without a restart.
These functions touch the ORM and must be called from synchronous code only.
"""
import threading
import time
from dataclasses import dataclass

from config.env_schema import config
from storage_engine.secrets import decrypt, CredentialsUnreadable

RELOAD_INTERVAL = 10.0


@dataclass(frozen=True)
class CredentialSnapshot:
    source: str          # 'db' | 'env'
    mode: str            # 'session' | 'mock'
    session_str: str
    chat_id: object      # 'me' | int | '@username'
    unreadable: bool
    api_id: int
    api_hash: str
    version: str         # changes whenever the credentials or chat change


_lock = threading.Lock()
_snapshot = None
_checked_at = 0.0
_user_snapshots = {}   # account_id -> CredentialSnapshot
_user_checked_at = {}  # account_id -> monotonic time of the last re-check


def parse_chat_id(value):
    value = (value or '').strip()
    if not value:
        return 'me'
    if value.lstrip('-').isdigit():
        return int(value)
    return value


def _build(row) -> CredentialSnapshot:
    chat_value = (row.chat_id if row else '') or config.TELEGRAM_STORAGE_CHAT_ID
    mode = row.auth_mode if row else 'session'
    session_str, unreadable, source = config.TELEGRAM_SESSION_STRING, False, 'env'
    if row is not None and row.session_string_enc:
        source = 'db'
        try:
            session_str = decrypt(row.session_string_enc)
        except CredentialsUnreadable:
            session_str, unreadable = '', True
    version = f"{row.updated_at.isoformat()}" if row is not None else 'env'
    return CredentialSnapshot(
        source=source, mode=mode, session_str=session_str, chat_id=parse_chat_id(chat_value),
        unreadable=unreadable, api_id=config.TELEGRAM_API_ID, api_hash=config.TELEGRAM_API_HASH,
        version=version,
    )


def get_snapshot(force: bool = False) -> CredentialSnapshot:
    global _snapshot, _checked_at
    from drive.models import StorageSettings

    with _lock:
        now = time.monotonic()
        if not force and _snapshot is not None and now - _checked_at < RELOAD_INTERVAL:
            return _snapshot
        updated_at = StorageSettings.objects.filter(pk=1).values_list('updated_at', flat=True).first()
        current_version = updated_at.isoformat() if updated_at else 'env'
        if force or _snapshot is None or _snapshot.version != current_version:
            _snapshot = _build(StorageSettings.objects.filter(pk=1).first())
        _checked_at = now
        return _snapshot


def get_account_snapshot(account_id: int, force: bool = False) -> CredentialSnapshot:
    """Same contract as get_snapshot() but for a user's own UserStorageAccount row."""
    global _user_snapshots, _user_checked_at
    from drive.models import UserStorageAccount

    with _lock:
        now = time.monotonic()
        snapshot = _user_snapshots.get(account_id)
        if not force and snapshot is not None and now - _user_checked_at.get(account_id, 0.0) < RELOAD_INTERVAL:
            return snapshot
        row = UserStorageAccount.objects.filter(pk=account_id).first()
        current_version = row.updated_at.isoformat() if row is not None and row.updated_at else 'user-empty'
        if force or snapshot is None or snapshot.version != current_version:
            snapshot = _build_user(row)
            _user_snapshots[account_id] = snapshot
        _user_checked_at[account_id] = now
        return snapshot


def _build_user(row) -> CredentialSnapshot:
    session_str, unreadable = '', False
    if row is not None and row.session_string_enc:
        try:
            session_str = decrypt(row.session_string_enc)
        except CredentialsUnreadable:
            session_str, unreadable = '', True
    chat_id = None
    if row is not None and row.channel_id and row.channel_access_hash:
        from telethon.tl.types import InputPeerChannel

        chat_id = InputPeerChannel(row.channel_id, row.channel_access_hash)
    version = row.updated_at.isoformat() if row is not None and row.updated_at else 'user-empty'
    return CredentialSnapshot(
        source='db', mode='session', session_str=session_str, chat_id=chat_id, unreadable=unreadable,
        api_id=config.TELEGRAM_API_ID, api_hash=config.TELEGRAM_API_HASH, version=version,
    )


def invalidate(account_id=None):
    """
    Forget cached snapshots so the next call re-reads the DB (used after edits and in tests).
    Without an account_id: the system snapshot and every user snapshot. With one: just that account.
    """
    global _snapshot, _checked_at
    with _lock:
        if account_id is None:
            _snapshot = None
            _checked_at = 0.0
            _user_snapshots.clear()
            _user_checked_at.clear()
        else:
            _user_snapshots.pop(account_id, None)
            _user_checked_at.pop(account_id, None)
