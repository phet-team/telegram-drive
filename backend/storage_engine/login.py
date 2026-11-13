"""
Server-side Telegram login ("Reconnect Telegram" wizard).

The in-progress login lives in the DB row (not in process memory) because
gunicorn requests can land on different workers: the not-yet-authorised Telethon session
and Telegram's phone_code_hash are stored Fernet-encrypted for at most 5 minutes.
The code and the 2-step password are passed straight to Telegram and never stored or logged.

Two targets are supported: the system singleton (StorageSettings, admin flow) and a
per-user UserStorageAccount row (the user's "Connect my Telegram" flow).
"""
import logging
from datetime import timedelta

from django.db import IntegrityError
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from telethon import errors as te

from config.env_schema import config
from drive.models import StorageSettings, UploadSession, UserStorageAccount
from storage_engine import client as engine_client, credentials, health
from storage_engine.errors import StorageUnavailable
from storage_engine.secrets import decrypt, encrypt, CredentialsUnreadable

logger = logging.getLogger(__name__)

PENDING_TTL = timedelta(minutes=5)

CHANNEL_TITLE = 'Telegram Drive Storage'
CHANNEL_ABOUT = 'Files stored by Telegram Drive. Deleting this channel deletes your files.'


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
        if row.pending_login_session_enc or row.pending_phone:  # expired: drop the half-login and the phone
            row.clear_pending_login()
            row.save(update_fields=row.PENDING_FIELDS)
        raise LoginError("No login in progress or it has expired. Start again.", status=400)
    try:
        return decrypt(row.pending_login_session_enc), row.pending_phone, decrypt(row.pending_code_hash)
    except CredentialsUnreadable as exc:
        raise LoginError("The pending login cannot be read. Start again.", status=400) from exc


@sensitive_variables('phone', 'session_str', 'code_hash')
def start(user, phone, target_row=None):
    @sensitive_variables('phone')
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

    row = target_row if target_row is not None else StorageSettings.get_solo()
    row.pending_login_session_enc = encrypt(session_str)
    row.pending_phone = phone
    row.pending_code_hash = encrypt(code_hash)
    row.pending_expires_at = timezone.now() + PENDING_TTL
    row.save(update_fields=row.PENDING_FIELDS)
    return int(PENDING_TTL.total_seconds())


@sensitive_variables('credentials_kw', 'session_str', 'phone', 'code_hash')
def _sign_in(row, **credentials_kw):
    """Signs in with the pending session. Returns ('ok', session, first_name) or ('password', session, None)."""
    session_str, phone, code_hash = _pending(row)

    @sensitive_variables('credentials_kw', 'session_str', 'phone', 'code_hash')
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


def _call_telethon_mapped(coro):
    try:
        return _run(coro)
    except te.FloodWaitError as exc:
        raise LoginError(f"Too many attempts. Wait {exc.seconds} seconds.", status=429, retry_after=exc.seconds) from exc
    except te.ChannelsTooMuchError as exc:
        raise LoginError("Your Telegram account has too many channels. Leave one and try again.", status=400) from exc
    except Exception as exc:
        _map_connection_error(exc)
        raise


def _create_channel(client):
    """Creates the user's private storage channel. Returns (channel_id, channel_access_hash)."""
    from telethon.tl.functions.channels import CreateChannelRequest

    res = _call_telethon_mapped(client(CreateChannelRequest(
        title=CHANNEL_TITLE,
        about=CHANNEL_ABOUT,
        broadcast=True,
    )))
    channel = res.chats[0]
    return channel.id, getattr(channel, 'access_hash', 0)


def _drop_inflight_uploads(target_row):
    """
    The account's channel changed: chunks of unfinished uploads went to the old channel, so those
    sessions can never complete correctly. Cancel them (own uploads reserve no quota) and forget
    cached chunks of this account.
    """
    UploadSession.objects.filter(storage_account=target_row, status='UPLOADING').update(status='CANCELLED')
    engine_client.purge_chunk_cache(f"user:{target_row.id}")


@sensitive_variables('session_str')
def _finish_user(user, session_str, target_row):
    """
    Completes the wizard for a per-user account: verifies the Telegram identity,
    refuses an account already linked elsewhere or files that live in another account,
    provisions the storage channel, then saves the row and probes the engine.
    """
    saved = False
    client = None
    try:
        try:
            client = _call_telethon_mapped(_open_client(session_str))
            me = _call_telethon_mapped(client.get_me())
            tg_user_id = me.id

            clash = UserStorageAccount.objects.exclude(pk=target_row.pk).filter(tg_user_id=tg_user_id).first()
            if clash is not None:
                raise LoginError("This Telegram account is already linked to another user.", status=409)

            if (target_row.tg_user_id is not None and target_row.tg_user_id != tg_user_id
                    and target_row.files.count() > 0):
                raise LoginError(
                    f"Your files are stored in another Telegram account ({target_row.tg_display_name}). "
                    "Reconnect that account, or delete those files first.", status=409)

            channel_changed = False
            if not target_row.channel_id or (target_row.tg_user_id != tg_user_id and target_row.files.count() == 0):
                target_row.channel_id, target_row.channel_access_hash = _create_channel(client)
                channel_changed = True

            first = getattr(me, 'first_name', '') or ''
            user_name = getattr(me, 'username', '') or ''
            display_name = f"{first} (@{user_name})" if user_name else first
            if not display_name:
                display_name = str(me.id)

            target_row.tg_user_id = tg_user_id
            target_row.tg_display_name = display_name
            target_row.session_string_enc = encrypt(session_str)
            target_row.connected_at = timezone.now()
            target_row.status = 'ok'
            target_row.clear_pending_login()
            try:
                target_row.save()
                saved = True
            except IntegrityError as exc:
                raise LoginError("This Telegram account is already linked to another user.", status=409) from exc

            if channel_changed:
                _drop_inflight_uploads(target_row)
            credentials.invalidate(account_id=target_row.id)
            health.reset(key=f"user:{target_row.id}")
        finally:
            if client is not None:
                try:
                    _run(client.disconnect())
                except Exception:
                    logger.warning("Disconnecting the login client failed", exc_info=True)
    except Exception:
        if not saved:
            logout_client(session_str)
            try:
                target_row.clear_pending_login()
                target_row.save(update_fields=target_row.PENDING_FIELDS)
            except Exception:
                logger.warning("Failed to clear pending login on failure", exc_info=True)
        raise

    from storage_engine.selftest import run_selftest  # local import: avoids a cycle at module load
    probe = run_selftest(1, account=target_row)
    if (not probe['ok'] and probe['reason'] == 'channel_unreachable'
            and target_row.files.count() == 0):
        # The channel is gone or was never joined: recreate it once and re-probe.
        client = None
        try:
            client = _call_telethon_mapped(_open_client(session_str))
            target_row.channel_id, target_row.channel_access_hash = _create_channel(client)
            target_row.save()
            _drop_inflight_uploads(target_row)
            credentials.invalidate(account_id=target_row.id)
            probe = run_selftest(1, account=target_row)
        except Exception:
            logger.warning("Recreating channel on selftest probe failure failed", exc_info=True)
        finally:
            if client is not None:
                try:
                    _run(client.disconnect())
                except Exception:
                    logger.warning("Disconnecting the login client failed", exc_info=True)

    logger.info("User storage session connected for account id=%s by user id=%s", target_row.id, user.id)
    return {
        'ok': True, 'account': display_name,
        'storage_ok': probe['ok'], 'storage_step': probe['failed_step'], 'storage_reason': probe['reason'],
    }


async def _open_client(session_str):
    client = _new_client(session_str)
    await client.connect()
    return client


def _finish(user, session_str, account, target_row=None):
    """Saves the new session, then probes storage with a send-and-delete message."""
    if isinstance(target_row, UserStorageAccount):
        return _finish_user(user, session_str, target_row)

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


@sensitive_variables('code', 'session_str')
def verify_code(user, code, target_row=None):
    row = target_row if target_row is not None else StorageSettings.get_solo()
    outcome, session_str, account = _sign_in(row, code=code.strip().replace(' ', ''))
    if outcome == 'password':
        row.pending_login_session_enc = encrypt(session_str)
        row.save(update_fields=['pending_login_session_enc'])
        return {'ok': False, 'needs_password': True}
    return _finish(user, session_str, account, target_row=target_row)


@sensitive_variables('password', 'session_str')
def verify_password(user, password, target_row=None):
    row = target_row if target_row is not None else StorageSettings.get_solo()
    _, session_str, account = _sign_in(row, password=password)
    return _finish(user, session_str, account, target_row=target_row)


def cancel(target_row=None):
    row = target_row if target_row is not None else StorageSettings.get_solo()
    row.clear_pending_login()
    row.save(update_fields=row.PENDING_FIELDS)


@sensitive_variables('session_str')
def logout_client(session_str):
    """
    Best-effort `client.log_out()` for the account behind `session_str`: at most 10 s,
    never raises, never blocks the caller (used on disconnect and before deleting a user).
    """
    if not session_str:
        return

    async def _logout():
        client = _new_client(session_str)
        await client.connect()
        try:
            await client.log_out()
        finally:
            await client.disconnect()

    try:
        engine_client.get_telethon_thread().run_coro(_logout(), timeout=10)
    except Exception:
        logger.warning("Telegram log_out failed; continuing without it", exc_info=True)
