"""
Server-side Telegram login ("Reconnect Telegram" wizard).

The in-progress login lives in the StorageSettings row (not in process memory) because
gunicorn requests can land on different workers: the not-yet-authorised Telethon session
and Telegram's phone_code_hash are stored Fernet-encrypted for at most 5 minutes.
The code and the 2-step password are passed straight to Telegram and never stored or logged.
"""
import logging
from datetime import timedelta

from django.utils import timezone
from telethon import errors as te

from config.env_schema import config
from drive.models import StorageSettings
from storage_engine import client as engine_client, credentials, health
from storage_engine.errors import StorageUnavailable
from storage_engine.secrets import decrypt, encrypt, CredentialsUnreadable

logger = logging.getLogger(__name__)

PENDING_TTL = timedelta(minutes=5)


class LoginError(Exception):
    """A wizard failure with a clear message and the HTTP status to return."""

    def __init__(self, message, status=400, retry_after=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.retry_after = retry_after


def _run(coro):
    return engine_client.get_telethon_thread().run_coro(coro, timeout=60)


def _new_client(session_str=''):
    if not config.TELEGRAM_API_ID or not config.TELEGRAM_API_HASH:
        raise LoginError("TELEGRAM_API_ID / TELEGRAM_API_HASH are not configured on the server.", status=400)
    return engine_client.build_telegram_client(
        session_str, config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH, allow_file_session=False
    )


def _map_connection_error(exc):
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        raise StorageUnavailable('telegram_unreachable') from exc
    raise exc


def _pending(row):
    """Returns (session_str, phone, code_hash) of a live pending login, or raises LoginError."""
    if (not row.pending_login_session_enc or not row.pending_expires_at
            or row.pending_expires_at <= timezone.now()):
        raise LoginError("No login in progress or it has expired. Start again.", status=400)
    try:
        return decrypt(row.pending_login_session_enc), row.pending_phone, decrypt(row.pending_code_hash)
    except CredentialsUnreadable as exc:
        raise LoginError("The pending login cannot be read. Start again.", status=400) from exc


def start(user, phone):
    async def _start():
        client = _new_client()
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
            return client.session.save(), sent.phone_code_hash
        finally:
            await client.disconnect()

    try:
        session_str, code_hash = _run(_start())
    except LoginError:
        raise
    except te.FloodWaitError as exc:
        raise LoginError(f"Telegram asks to wait {exc.seconds} seconds before another code.",
                         status=429, retry_after=exc.seconds) from exc
    except te.PhoneNumberFloodError as exc:
        raise LoginError("Too many code requests for this phone number. Try again later.", status=429) from exc
    except te.PhoneNumberInvalidError as exc:
        raise LoginError("Telegram rejected the phone number. Use the international format, e.g. +66...", 400) from exc
    except te.ApiIdInvalidError as exc:
        raise LoginError("TELEGRAM_API_ID / TELEGRAM_API_HASH were rejected by Telegram.", 400) from exc
    except Exception as exc:
        _map_connection_error(exc)

    row = StorageSettings.get_solo()
    row.pending_login_session_enc = encrypt(session_str)
    row.pending_phone = phone
    row.pending_code_hash = encrypt(code_hash)
    row.pending_expires_at = timezone.now() + PENDING_TTL
    row.save(update_fields=StorageSettings.PENDING_FIELDS)
    return int(PENDING_TTL.total_seconds())


def _sign_in(row, **credentials_kw):
    """Signs in with the pending session. Returns ('ok', session, first_name) or ('password', session, None)."""
    session_str, phone, code_hash = _pending(row)

    async def _verify():
        client = _new_client(session_str)
        await client.connect()
        try:
            try:
                if 'password' in credentials_kw:
                    await client.sign_in(password=credentials_kw['password'])
                else:
                    await client.sign_in(phone=phone, code=credentials_kw['code'], phone_code_hash=code_hash)
            except te.SessionPasswordNeededError:
                return 'password', client.session.save(), None
            me = await client.get_me()
            return 'ok', client.session.save(), (getattr(me, 'first_name', '') or '')
        finally:
            await client.disconnect()

    try:
        return _run(_verify())
    except LoginError:
        raise
    except (te.PhoneCodeInvalidError, te.PhoneCodeEmptyError) as exc:
        raise LoginError("The code is incorrect.", 400) from exc
    except (te.PhoneCodeExpiredError, te.PhoneCodeHashEmptyError) as exc:
        raise LoginError("The code has expired. Start again to get a new one.", 400) from exc
    except te.PasswordHashInvalidError as exc:
        raise LoginError("The 2-step verification password is incorrect.", 400) from exc
    except te.FloodWaitError as exc:
        raise LoginError(f"Too many attempts. Wait {exc.seconds} seconds.", status=429, retry_after=exc.seconds) from exc
    except Exception as exc:
        _map_connection_error(exc)


def _finish(user, session_str, account):
    """Saves the new session, then probes storage with a send-and-delete message."""
    row = StorageSettings.get_solo()
    row.session_string_enc = encrypt(session_str)
    row.auth_mode = StorageSettings.AUTH_SESSION
    row.clear_pending_login()
    row.updated_by = user
    row.save()  # includes updated_at: every worker reloads the credentials
    credentials.invalidate()
    health.reset()
    logger.info("Telegram storage session replaced by user id=%s via the reconnect wizard", user.id)

    from storage_engine.selftest import run_selftest  # local import: avoids a cycle at module load
    probe = run_selftest(1)  # a successful upload also reports ok -> sends "recovered" if it was down
    return {
        'ok': True, 'account': account,
        'storage_ok': probe['ok'], 'storage_step': probe['failed_step'], 'storage_reason': probe['reason'],
    }


def verify_code(user, code):
    row = StorageSettings.get_solo()
    outcome, session_str, account = _sign_in(row, code=code.strip().replace(' ', ''))
    if outcome == 'password':
        row.pending_login_session_enc = encrypt(session_str)
        row.save(update_fields=['pending_login_session_enc'])
        return {'ok': False, 'needs_password': True}
    return _finish(user, session_str, account)


def verify_password(user, password):
    row = StorageSettings.get_solo()
    _, session_str, account = _sign_in(row, password=password)
    return _finish(user, session_str, account)


def cancel():
    row = StorageSettings.get_solo()
    row.clear_pending_login()
    row.save(update_fields=StorageSettings.PENDING_FIELDS)
