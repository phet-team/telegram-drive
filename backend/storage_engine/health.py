"""
Process-local storage health cache (30 s) plus the glue that feeds results into the
alert state machine. A failure seen by any request (upload, download, health probe)
updates the cache, so `UploadViewSet.initiate` can refuse early with a 503.
"""
import threading
import time

from storage_engine import alerts
from storage_engine.errors import StorageEngineError, StorageUnavailable

HEALTH_TTL = 30.0          # seconds a cached result is trusted
OK_REPORT_INTERVAL = 30.0  # successful operations touch the DB at most this often

_lock = threading.Lock()
_check_lock = threading.Lock()
_state = {'ok': None, 'reason': '', 'at': 0.0}
_last_ok_report = 0.0


def reset():
    """Forget the cached result (used after a reconnect and in tests)."""
    global _last_ok_report
    with _lock:
        _state.update(ok=None, reason='', at=0.0)
        _last_ok_report = 0.0


def get_cached():
    """Returns (ok, reason) when a result younger than HEALTH_TTL exists, else None."""
    with _lock:
        if _state['ok'] is not None and time.monotonic() - _state['at'] < HEALTH_TTL:
            return _state['ok'], _state['reason']
    return None


def _set(ok, reason=''):
    with _lock:
        _state.update(ok=ok, reason=reason, at=time.monotonic())


def record_failure(reason):
    _set(False, reason)
    alerts.report_failure(reason)


def record_success(force=False):
    global _last_ok_report
    with _lock:
        was_down = _state['ok'] is False
    _set(True)
    now = time.monotonic()
    if force or was_down or now - _last_ok_report >= OK_REPORT_INTERVAL:
        _last_ok_report = now
        alerts.report_ok()


def raise_if_known_down():
    """503 early when the last health result (< 30 s old) says storage is down."""
    cached = get_cached()
    if cached is not None and cached[0] is False:
        raise StorageUnavailable(cached[1])


def check_health(force=False):
    """Returns (ok, reason). Cheap: connected client + get_me(), cached for 30 s."""
    from storage_engine.client import get_storage_engine

    with _check_lock:
        if not force:
            cached = get_cached()
            if cached is not None:
                return cached
        try:
            get_storage_engine().health_check()
        except StorageUnavailable as exc:
            return False, exc.reason
        except StorageEngineError:
            _set(False, 'unexpected_error')
            return False, 'unexpected_error'
        return True, ''
