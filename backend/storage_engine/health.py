"""
Process-local storage health cache (30 s) keyed by 'system' or 'user:<account_id>' plus the
glue that feeds results into the alert state machine. A failure seen by any request (upload,
download, health probe) updates the cache, so `UploadViewSet.initiate` can refuse early with
a 503. A `user:` key additionally mirrors its status onto the UserStorageAccount row using
filter().update() so `updated_at` (and therefore the credential cache) is not touched.
"""
import logging
import threading
import time

from storage_engine import alerts
from storage_engine.errors import StorageEngineError, StorageUnavailable

logger = logging.getLogger(__name__)

HEALTH_TTL = 30.0          # seconds a cached result is trusted
OK_REPORT_INTERVAL = 30.0  # successful operations touch the DB/alerts at most this often
DB_REPORT_INTERVAL = 30.0  # repeated 'down' writes to one user row at most this often

_lock = threading.Lock()
_check_locks = {}  # key -> lock, so a slow probe on one account never blocks another
_check_locks_guard = threading.Lock()
_states = {}  # key -> {'ok': bool | None, 'reason': str, 'at': float, 'last_db_report': float}


def _check_lock_for(key):
    with _check_locks_guard:
        return _check_locks.setdefault(key, threading.Lock())


def _state_for(key):
    return _states.setdefault(key, {'ok': None, 'reason': '', 'at': 0.0, 'last_db_report': 0.0})


def reset(key=None):
    """Forget cached results (used after a reconnect and in tests)."""
    with _check_locks_guard:
        if key is None:
            _check_locks.clear()
        else:
            _check_locks.pop(key, None)
    with _lock:
        if key is None:
            _states.clear()
        else:
            _states.pop(key, None)


def get_cached(key='system'):
    """Returns (ok, reason) when a result younger than HEALTH_TTL exists, else None."""
    with _lock:
        state = _states.get(key)
        if state is not None and state['ok'] is not None and time.monotonic() - state['at'] < HEALTH_TTL:
            return state['ok'], state['reason']
    return None


def _set(ok, reason='', key='system'):
    with _lock:
        _state_for(key).update(ok=ok, reason=reason, at=time.monotonic())


def _account_id_for(key):
    return int(key.split(':', 1)[1])


def _db_write(account_id, status, reason):
    """Mirror the status onto the user row; update() leaves `updated_at` alone by design."""
    from django.utils import timezone
    from drive.models import UserStorageAccount

    try:
        UserStorageAccount.objects.filter(pk=account_id).update(
            status=status, last_check_at=timezone.now(), last_check_reason=reason)
    except Exception:  # never let a status mirror hide the original storage error
        logger.warning("Could not write storage status for account %s", account_id, exc_info=True)


def record_failure(reason, key='system'):
    with _lock:
        state = _state_for(key)
        already_down_same = state['ok'] is False and state['reason'] == reason
        state.update(ok=False, reason=reason, at=time.monotonic())
        last_db_report = state['last_db_report']
    if key == 'system':
        alerts.report_failure(reason)
    elif key.startswith('user:'):
        now = time.monotonic()
        if not already_down_same or now - last_db_report >= DB_REPORT_INTERVAL:
            _db_write(_account_id_for(key), 'down', reason)
            state['last_db_report'] = now


def record_success(force=False, key='system'):
    with _lock:
        state = _state_for(key)
        was_down = state['ok'] is False
        state.update(ok=True, reason='', at=time.monotonic())
        last_db_report = state['last_db_report']
    now = time.monotonic()
    if key == 'system':
        if force or was_down or now - last_db_report >= OK_REPORT_INTERVAL:
            state['last_db_report'] = now
            alerts.report_ok()
    elif key.startswith('user:'):
        if force or was_down or now - last_db_report >= OK_REPORT_INTERVAL:
            _db_write(_account_id_for(key), 'ok', '')
            state['last_db_report'] = now


def raise_if_known_down(key='system'):
    """503 early when the last health result (< 30 s old) says storage is down."""
    cached = get_cached(key=key)
    if cached is not None and cached[0] is False:
        raise StorageUnavailable(cached[1])


def check_health(account=None, force=False):
    """Returns (ok, reason). Cheap: connected client + get_me(), cached for 30 s."""
    from storage_engine.client import get_storage_engine

    key = 'system' if account is None else f"user:{account.id if hasattr(account, 'id') else account}"
    with _check_lock_for(key):
        if not force:
            cached = get_cached(key=key)
            if cached is not None:
                return cached
        try:
            get_storage_engine(account=account).health_check()
        except StorageUnavailable as exc:
            return False, exc.reason
        except StorageEngineError:
            record_failure('unexpected_error', key=key)
            return False, 'unexpected_error'
        return True, ''
