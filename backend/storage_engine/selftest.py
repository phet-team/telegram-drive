import hashlib
import logging
import os
import time

from storage_engine.client import get_storage_engine
from storage_engine.errors import StorageUnavailable

logger = logging.getLogger(__name__)


def run_selftest(size_mb: int, account=None) -> dict:
    """
    Upload random bytes, download them, compare sha256, delete the message.
    `account` (a UserStorageAccount or id) selects the per-user engine; None is system.
    Returns {"ok", "size_mb", "up_s", "down_s", "delete_s", "failed_step", "reason"};
    `failed_step` is the first failing step: upload | download | compare | delete.
    """
    result = {'ok': False, 'size_mb': size_mb, 'up_s': None, 'down_s': None, 'delete_s': None,
              'failed_step': None, 'reason': ''}
    engine = get_storage_engine(account=account)
    payload = os.urandom(size_mb * 1024 * 1024)
    expected = hashlib.sha256(payload).hexdigest()
    message_id = None
    step = 'upload'
    try:
        started = time.monotonic()
        message_id, file_id = engine.upload_chunk(payload, f"selftest_{size_mb}mb.bin")
        result['up_s'] = round(time.monotonic() - started, 2)

        step = 'download'
        started = time.monotonic()
        downloaded = engine.download_chunk(file_id, message_id)
        result['down_s'] = round(time.monotonic() - started, 2)

        step = 'compare'
        if hashlib.sha256(downloaded).hexdigest() != expected:
            raise ValueError("downloaded bytes differ from the uploaded bytes")

        step = 'delete'
        started = time.monotonic()
        deleted = engine.delete_chunk(message_id)
        result['delete_s'] = round(time.monotonic() - started, 2)
        message_id = None
        if not deleted:
            raise ValueError("delete_chunk reported failure")
        result['ok'] = True
    except StorageUnavailable as exc:
        result.update(failed_step=step, reason=exc.reason)
    except Exception as exc:
        logger.warning("Storage self-test failed at step=%s", step, exc_info=True)
        # Class name only: the message of an unclassified Telethon error can carry peer ids / access hashes.
        result.update(failed_step=step, reason=type(exc).__name__)
    finally:
        if message_id is not None:  # a later step failed: do not leave the test message behind
            try:
                engine.delete_chunk(message_id)
            except Exception:
                logger.warning("Self-test cleanup could not delete message %s", message_id)
    return result
